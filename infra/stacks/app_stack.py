"""AppStack — Lambdas, ECS Fargate, ALB. Depends on DataStack.

This stack deploys fast (~2 min) and can be updated independently
when only application code changes.
"""

from aws_cdk import (
    Duration,
    Stack,
    aws_ec2 as ec2,
    aws_ecr_assets as ecr_assets,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_kinesis as kinesis,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_rds as rds,
    aws_secretsmanager as sm,
    aws_sqs as sqs,
)
from constructs import Construct


class AppStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str,
        vpc: ec2.Vpc,
        db_security_group: ec2.SecurityGroup,
        db_proxy: rds.DatabaseProxy,
        db_secret: sm.ISecret,
        read_replica: rds.DatabaseInstanceReadReplica,
        weather_stream: kinesis.Stream,
        alerts_queue: sqs.Queue,
        dlq: sqs.Queue,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Build DB URLs using secret fields resolved at deploy time
        db_user = db_secret.secret_value_from_json("username").unsafe_unwrap()
        db_pass = db_secret.secret_value_from_json("password").unsafe_unwrap()
        proxy_url = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_proxy.endpoint}:5432/agrobot"
        replica_url = f"postgresql+asyncpg://{db_user}:{db_pass}@{read_replica.instance_endpoint.hostname}:5432/agrobot"

        jwt_secret = db_secret.secret_value_from_json("password").unsafe_unwrap()

        common_env = {
            "AGROBOT_DATABASE_URL": proxy_url,
            "AGROBOT_REPLICA_DATABASE_URL": replica_url,
            "AGROBOT_JWT_SECRET_KEY": jwt_secret,
            "AGROBOT_AWS_REGION": self.region,
            "AGROBOT_ENVIRONMENT": "production",
            "POWERTOOLS_TRACE_DISABLED": "true",
        }

        # Lambda Docker image (includes all Python dependencies)
        lambda_image = lambda_.DockerImageCode.from_image_asset(
            ".",
            file="Dockerfile.lambda",
            platform=ecr_assets.Platform.LINUX_AMD64,
        )

        # ── Lambda: Matching Engine ─────────────────────────────
        matching_lambda = lambda_.DockerImageFunction(
            self,
            "MatchingEngineV2",
            code=lambda_image,
            timeout=Duration.seconds(60),
            memory_size=256,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[db_security_group],
            environment={
                **common_env,
                "AGROBOT_SQS_QUEUE_URL": alerts_queue.queue_url,
                "POWERTOOLS_SERVICE_NAME": "matching-engine",
                "POWERTOOLS_METRICS_NAMESPACE": "Agrobot",
                "CMD": "src.lambdas.matching.handler.lambda_handler",
            },
        )

        matching_lambda.add_event_source(
            event_sources.KinesisEventSource(
                weather_stream,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=100,
                max_batching_window=Duration.seconds(5),
                parallelization_factor=1,
                bisect_batch_on_error=True,
                retry_attempts=3,
            )
        )

        alerts_queue.grant_send_messages(matching_lambda)
        weather_stream.grant_read(matching_lambda)
        db_secret.grant_read(matching_lambda)

        # ── Lambda: Dispatcher ───────────────────────────────────
        dispatcher_lambda = lambda_.DockerImageFunction(
            self,
            "DispatcherV2",
            code=lambda_.DockerImageCode.from_image_asset(
                ".",
                file="Dockerfile.lambda",
                platform=ecr_assets.Platform.LINUX_AMD64,
                cmd=["src.lambdas.dispatcher.handler.lambda_handler"],
            ),
            timeout=Duration.seconds(30),
            memory_size=256,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[db_security_group],
            environment={
                **common_env,
                "POWERTOOLS_SERVICE_NAME": "dispatcher",
                "POWERTOOLS_METRICS_NAMESPACE": "Agrobot",
            },
        )

        dispatcher_lambda.add_event_source(
            event_sources.SqsEventSource(
                alerts_queue,
                batch_size=10,
                max_batching_window=Duration.seconds(5),
                report_batch_item_failures=True,
            )
        )

        alerts_queue.grant_consume_messages(dispatcher_lambda)
        db_secret.grant_read(dispatcher_lambda)

        # ── ECS Fargate (API) ────────────────────────────────────
        cluster = ecs.Cluster(self, "AgrobotCluster", vpc=vpc)

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "AgrobotApi",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(".", platform=ecr_assets.Platform.LINUX_AMD64),
                container_port=8000,
                environment={
                    **common_env,
                    "AGROBOT_KINESIS_STREAM_NAME": weather_stream.stream_name,
                    "AGROBOT_SQS_QUEUE_URL": alerts_queue.queue_url,
                    "AGROBOT_SQS_DLQ_URL": dlq.queue_url,
                },
            ),
            public_load_balancer=True,
        )

        service.target_group.configure_health_check(path="/health")

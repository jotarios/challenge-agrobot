"""Main Agrobot CDK stack.

Infrastructure:
  VPC → RDS (PostgreSQL + Read Replica + 2x RDS Proxy) → Kinesis (2 shards)
  → Lambda Matching Engine → SQS (+ DLQ) → Lambda Dispatcher
  → ECS Fargate (API) → API Gateway

  ┌─────────────────────────────────────────────────────────────┐
  │ VPC                                                         │
  │  ┌──────────┐   ┌──────────┐   ┌──────────────────────┐   │
  │  │ RDS      │   │ RDS      │   │ ECS Fargate          │   │
  │  │ Primary  │   │ Replica  │   │ (FastAPI)             │   │
  │  └────┬─────┘   └────┬─────┘   └──────────┬───────────┘   │
  │       │              │                     │               │
  │  ┌────▼─────┐   ┌────▼─────┐        ┌─────▼─────┐        │
  │  │ RDS Proxy│   │ RDS Proxy│        │ API       │        │
  │  │ (write)  │   │ (read)   │        │ Gateway   │        │
  │  └──────────┘   └──────────┘        └───────────┘        │
  └─────────────────────────────────────────────────────────────┘

  ┌──────────┐   ┌──────────────────┐   ┌──────────┐   ┌──────────────────┐
  │ Kinesis  │──▶│ Matching Engine  │──▶│ SQS      │──▶│ Dispatcher       │
  │ (2 shard)│   │ Lambda           │   │ (+ DLQ)  │   │ Lambda           │
  └──────────┘   └──────────────────┘   └──────────┘   └──────────────────┘

Note: DMS is excluded from CDK (configured manually per runbook).
"""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
    aws_kinesis as kinesis,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_rds as rds,
    aws_sqs as sqs,
)
from constructs import Construct


class AgrobotStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── VPC ──────────────────────────────────────────────────
        vpc = ec2.Vpc(
            self,
            "AgrobotVpc",
            max_azs=2,
            nat_gateways=1,
        )

        # ── RDS PostgreSQL ───────────────────────────────────────
        db_security_group = ec2.SecurityGroup(
            self, "DbSecurityGroup", vpc=vpc, allow_all_outbound=True
        )
        db_security_group.add_ingress_rule(
            ec2.Peer.ipv4(vpc.vpc_cidr_block), ec2.Port.tcp(5432)
        )

        parameter_group = rds.ParameterGroup(
            self,
            "AgrobotParamGroup",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_1
            ),
            parameters={"rds.logical_replication": "1"},
        )

        db_instance = rds.DatabaseInstance(
            self,
            "AgrobotDb",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_1
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MEDIUM
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[db_security_group],
            parameter_group=parameter_group,
            database_name="agrobot",
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
        )

        # Read Replica
        read_replica = rds.DatabaseInstanceReadReplica(
            self,
            "AgrobotDbReplica",
            source_database_instance=db_instance,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MEDIUM
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[db_security_group],
            removal_policy=RemovalPolicy.DESTROY,
        )

        # RDS Proxy (primary - write)
        primary_proxy = rds.DatabaseProxy(
            self,
            "AgrobotPrimaryProxy",
            proxy_target=rds.ProxyTarget.from_instance(db_instance),
            secrets=[db_instance.secret],
            vpc=vpc,
            security_groups=[db_security_group],
            require_tls=False,
        )

        # RDS Proxy (replica - read)
        replica_proxy = rds.DatabaseProxy(
            self,
            "AgrobotReplicaProxy",
            proxy_target=rds.ProxyTarget.from_instance(read_replica),
            secrets=[db_instance.secret],
            vpc=vpc,
            security_groups=[db_security_group],
            require_tls=False,
        )

        # ── Kinesis Stream ───────────────────────────────────────
        weather_stream = kinesis.Stream(
            self,
            "WeatherEventsStream",
            stream_name="weather-events",
            shard_count=2,
            retention_period=Duration.hours(24),
        )

        # ── SQS Queue + DLQ ─────────────────────────────────────
        dlq = sqs.Queue(
            self,
            "AlertsDlq",
            queue_name="agrobot-alerts-dlq",
            retention_period=Duration.days(14),
        )

        alerts_queue = sqs.Queue(
            self,
            "AlertsQueue",
            queue_name="agrobot-alerts",
            visibility_timeout=Duration.seconds(180),  # 6x Dispatcher timeout (30s)
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=dlq),
        )

        # ── Lambda: Matching Engine ─────────────────────────────
        matching_lambda = lambda_.Function(
            self,
            "MatchingEngine",
            function_name="agrobot-matching-engine",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="src.lambdas.matching.handler.lambda_handler",
            code=lambda_.Code.from_asset(
                ".",
                exclude=["infra/*", "tests/*", "cdk.out/*", "node_modules/*", ".git/*"],
            ),
            timeout=Duration.seconds(60),
            memory_size=256,
            reserved_concurrent_executions=2,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[db_security_group],
            environment={
                "AGROBOT_REPLICA_DATABASE_URL": f"postgresql+asyncpg://{{resolve}}@{replica_proxy.endpoint}:5432/agrobot",
                "AGROBOT_DATABASE_URL": f"postgresql+asyncpg://{{resolve}}@{primary_proxy.endpoint}:5432/agrobot",
                "AGROBOT_SQS_QUEUE_URL": alerts_queue.queue_url,
                "AGROBOT_AWS_REGION": self.region,
                "AGROBOT_ENVIRONMENT": "production",
                "POWERTOOLS_SERVICE_NAME": "matching-engine",
                "POWERTOOLS_METRICS_NAMESPACE": "Agrobot",
            },
        )

        # Kinesis → Matching Engine event source
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

        # ── Lambda: Dispatcher ───────────────────────────────────
        dispatcher_lambda = lambda_.Function(
            self,
            "Dispatcher",
            function_name="agrobot-dispatcher",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="src.lambdas.dispatcher.handler.lambda_handler",
            code=lambda_.Code.from_asset(
                ".",
                exclude=["infra/*", "tests/*", "cdk.out/*", "node_modules/*", ".git/*"],
            ),
            timeout=Duration.seconds(30),
            memory_size=256,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[db_security_group],
            environment={
                "AGROBOT_DATABASE_URL": f"postgresql+asyncpg://{{resolve}}@{primary_proxy.endpoint}:5432/agrobot",
                "AGROBOT_REPLICA_DATABASE_URL": f"postgresql+asyncpg://{{resolve}}@{replica_proxy.endpoint}:5432/agrobot",
                "AGROBOT_AWS_REGION": self.region,
                "AGROBOT_ENVIRONMENT": "production",
                "POWERTOOLS_SERVICE_NAME": "dispatcher",
                "POWERTOOLS_METRICS_NAMESPACE": "Agrobot",
            },
        )

        # SQS → Dispatcher event source
        dispatcher_lambda.add_event_source(
            event_sources.SqsEventSource(
                alerts_queue,
                batch_size=10,
                max_batching_window=Duration.seconds(5),
                report_batch_item_failures=True,
            )
        )

        alerts_queue.grant_consume_messages(dispatcher_lambda)

        # ── ECS Fargate (API) ────────────────────────────────────
        cluster = ecs.Cluster(self, "AgrobotCluster", vpc=vpc)

        ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "AgrobotApi",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("."),
                container_port=8000,
                environment={
                    "AGROBOT_DATABASE_URL": f"postgresql+asyncpg://{{resolve}}@{primary_proxy.endpoint}:5432/agrobot",
                    "AGROBOT_AWS_REGION": self.region,
                    "AGROBOT_ENVIRONMENT": "production",
                    "AGROBOT_KINESIS_STREAM_NAME": weather_stream.stream_name,
                    "AGROBOT_SQS_QUEUE_URL": alerts_queue.queue_url,
                    "AGROBOT_SQS_DLQ_URL": dlq.queue_url,
                },
            ),
            public_load_balancer=True,
        )

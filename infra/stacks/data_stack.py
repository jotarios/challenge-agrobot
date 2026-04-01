"""DataStack — RDS, RDS Proxy, Kinesis, SQS. Depends on NetworkStack."""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_kinesis as kinesis,
    aws_rds as rds,
    aws_sqs as sqs,
)
from constructs import Construct


class DataStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str,
        vpc: ec2.Vpc,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Security Group ───────────────────────────────────────
        self.db_security_group = ec2.SecurityGroup(
            self, "DbSecurityGroup", vpc=vpc, allow_all_outbound=True
        )
        self.db_security_group.add_ingress_rule(
            ec2.Peer.ipv4(vpc.vpc_cidr_block), ec2.Port.tcp(5432)
        )

        # ── RDS PostgreSQL ───────────────────────────────────────
        parameter_group = rds.ParameterGroup(
            self,
            "AgrobotParamGroup",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_3
            ),
            parameters={"rds.logical_replication": "1"},
        )

        self.db_instance = rds.DatabaseInstance(
            self,
            "AgrobotDb",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_3
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MEDIUM
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[self.db_security_group],
            parameter_group=parameter_group,
            database_name="agrobot",
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
        )

        # Read Replica
        self.read_replica = rds.DatabaseInstanceReadReplica(
            self,
            "AgrobotDbReplica",
            source_database_instance=self.db_instance,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MEDIUM
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[self.db_security_group],
            removal_policy=RemovalPolicy.DESTROY,
        )

        # RDS Proxy
        self.db_proxy = rds.DatabaseProxy(
            self,
            "AgrobotProxy",
            proxy_target=rds.ProxyTarget.from_instance(self.db_instance),
            secrets=[self.db_instance.secret],
            vpc=vpc,
            security_groups=[self.db_security_group],
            require_tls=False,
        )

        # ── Kinesis Stream ───────────────────────────────────────
        self.weather_stream = kinesis.Stream(
            self,
            "WeatherEventsStream",
            stream_name="weather-events",
            shard_count=2,
            retention_period=Duration.hours(24),
        )

        # ── SQS Queue + DLQ ─────────────────────────────────────
        self.dlq = sqs.Queue(
            self,
            "AlertsDlq",
            queue_name="agrobot-alerts-dlq",
            retention_period=Duration.days(14),
        )

        self.alerts_queue = sqs.Queue(
            self,
            "AlertsQueue",
            queue_name="agrobot-alerts",
            visibility_timeout=Duration.seconds(180),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=self.dlq),
        )

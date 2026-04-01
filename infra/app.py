#!/usr/bin/env python3
"""CDK application entry point.

Three stacks deployed in order:
  1. NetworkStack — VPC, security groups (rarely changes)
  2. DataStack    — RDS, RDS Proxy, Kinesis, SQS (depends on Network)
  3. AppStack     — Lambdas, ECS Fargate, ALB (depends on Data, deploys fast)
"""

import aws_cdk as cdk

from infra.stacks.network_stack import NetworkStack
from infra.stacks.data_stack import DataStack
from infra.stacks.app_stack import AppStack

app = cdk.App()
env = cdk.Environment(region="us-east-1")

network = NetworkStack(app, "AgrobotNetworkStack", env=env)

data = DataStack(
    app, "AgrobotDataStack",
    vpc=network.vpc,
    env=env,
)
data.add_dependency(network)

app_stack = AppStack(
    app, "AgrobotAppStack",
    vpc=network.vpc,
    db_security_group=data.db_security_group,
    db_proxy=data.db_proxy,
    db_secret=data.db_instance.secret,
    read_replica=data.read_replica,
    weather_stream=data.weather_stream,
    alerts_queue=data.alerts_queue,
    dlq=data.dlq,
    env=env,
)
app_stack.add_dependency(data)

app.synth()

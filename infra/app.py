#!/usr/bin/env python3
"""CDK application entry point."""

import aws_cdk as cdk

from infra.stacks.agrobot_stack import AgrobotStack

app = cdk.App()
AgrobotStack(app, "AgrobotStack", env=cdk.Environment(region="us-east-1"))
app.synth()

#
# This just builds the lambda package we want to deploy
#
resource "null_resource" "prepare_lambda_package" {
  triggers = {
    # TODO: we would have to check the md5sum of a lot of files...
    #       maybe md5sum of folder? research!
    run_every_time = "${timestamp()}"
  }

  provisioner "local-exec" {
    # working_dir only for setup.cfg python pip bug
    working_dir = "${path.module}/../lambda"
    command     = "pip3 install -r requirements-lambda.txt -t lib"
  }

  provisioner "local-exec" {
    command = "rm -rf ${path.module}/../lambda-sns-to-snow.zip"
  }

  provisioner "local-exec" {
    command = "rm -rf /tmp/tf-lambda && mkdir -p /tmp/tf-lambda && cp -r ${path.module}/../lambda /tmp/tf-lambda/lambda"
  }

  provisioner "local-exec" {
    command = "find  /tmp/tf-lambda -type d -exec chmod 755 {} \\;"
  }

  provisioner "local-exec" {
    command = "find  /tmp/tf-lambda -type f -exec chmod 644 {} \\;"
  }
}

data "archive_file" "package_code_for_lambda" {
  type        = "zip"
  # Using this in a submodule is confusing when it comes to the path since
  # TF utilizes the repo clone by linking to it. This makes it much less
  # confusing.
  output_path = "/tmp/tf-lambda/lambda-sns-to-snow.zip"
  # The source_dir doesn't like ${path.module} or doesn't find the right one
  # hence we copy the entire path to a more reliable location
  source_dir  = "/tmp/tf-lambda/lambda"

  depends_on = ["null_resource.prepare_lambda_package"]
}

#
# Shared by all regions
#
resource "aws_iam_role" "lambda_config_sqs_to_snow_role" {
  name = "lambda_config_sqs_to_snow_role"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      }
    }
  ]
}
EOF
}

data "aws_iam_policy_document" "lambda_s3_config_bucket_permissions" {
  statement {
    actions = ["s3:ListBucket"],
    resources = ["arn:aws:s3:::org-config"]
  },

  statement {
    actions = ["s3:Get*"],
    resources = ["arn:aws:s3:::org-config/*"]
  }
}

resource "aws_iam_role_policy" "lambda_iam_s3_policy" {
  name = "lambda_iam_policy_to_access_s3_config_bucket"

  role   = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"
  policy = "${data.aws_iam_policy_document.lambda_s3_config_bucket_permissions.json}"
}

data "aws_iam_policy_document" "lambda_sqs_permissions" {
  statement {
    actions = [
        "sqs:ReceiveMessage",
        "sqs:SendMessage",
        "sqs:SendMessageBatch",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
    ]
    # TODO: make queue name a variable
    resources = ["arn:aws:sqs:*:${var.master_aws_account_id}:aws-config-to-snow-queue"]
  }
}

resource "aws_iam_role_policy" "lambda_sqs_policy" {
  name = "lambda_iam_policy_to_access_sqs"

  role   = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"
  policy = "${data.aws_iam_policy_document.lambda_sqs_permissions.json}"
}

data "aws_iam_policy_document" "lambda_secret_permissions" {
  statement {
    actions = [
                "secretsmanager:GetRandomPassword",
                "secretsmanager:GetResourcePolicy",
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret",
                "secretsmanager:ListSecrets",
                "secretsmanager:ListSecretVersionIds"
            ],
    resources = [
        "arn:aws:secretsmanager:*:*:secret:${var.snow_secret}*"
    ]
    # TODO: make queue name a variable
    # resources = ["arn:aws:secretsmanager:*:${var.master_aws_account_id}:secret:${var.snow_secret}"]
  }
}

resource "aws_iam_role_policy" "lambda_secret_policy" {
  name = "lambda_iam_policy_to_access_secret"

  role   = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"
  policy = "${data.aws_iam_policy_document.lambda_secret_permissions.json}"
}

#
# actual deployment
#
module "deploy-snow-lambda-us-east-1" {
  source = "./multi-region-lambda"

  this_aws_region         = "us-east-1"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.us-east-1"
  }
}

module "deploy-snow-lambda-us-west-1" {
  source = "./multi-region-lambda"

  this_aws_region         = "us-west-1"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.us-west-1"
  }
}

module "deploy-snow-lambda-us-west-2" {
  source = "./multi-region-lambda"

  this_aws_region         = "us-west-2"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.us-west-2"
  }
}

module "deploy-snow-lambda-eu-west-1" {
  source = "./multi-region-lambda"

  this_aws_region         = "eu-west-1"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.eu-west-1"
  }
}

module "deploy-snow-lambda-eu-west-2" {
  source = "./multi-region-lambda"

  this_aws_region         = "eu-west-2"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.eu-west-2"
  }
}

module "deploy-snow-lambda-ap-southeast-2" {
  source = "./multi-region-lambda"

  this_aws_region         = "ap-southeast-2"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.ap-southeast-2"
  }
}

module "deploy-snow-lambda-ca-central-1" {
  source = "./multi-region-lambda"

  this_aws_region         = "ca-central-1"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.ca-central-1"
  }
}

module "deploy-snow-lambda-ap-northeast-2" {
  source                  = "./multi-region-lambda"
  this_aws_region         = "ap-northeast-2"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.ap-northeast-2"
  }
}

module "deploy-snow-lambda-us-east-2" {
  source                  = "./multi-region-lambda"
  this_aws_region         = "us-east-2"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.us-east-2"
  }
}

module "deploy-snow-lambda-ap-southeast-1" {
  source                  = "./multi-region-lambda"
  this_aws_region         = "ap-southeast-1"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.ap-southeast-1"
  }
}

module "deploy-snow-lambda-eu-central-1" {
  source                  = "./multi-region-lambda"
  this_aws_region         = "eu-central-1"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.eu-central-1"
  }
}

module "deploy-snow-lambda-sa-east-1" {
  source                  = "./multi-region-lambda"
  this_aws_region         = "sa-east-1"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.sa-east-1"
  }
}

module "deploy-snow-lambda-ap-south-1" {
  source                  = "./multi-region-lambda"
  this_aws_region         = "ap-south-1"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.ap-south-1"
  }
}

module "deploy-snow-lambda-ap-northeast-1" {
  source                  = "./multi-region-lambda"
  this_aws_region         = "ap-northeast-1"
  snow_secret             = "${var.snow_secret}"
  lambda_source_code_hash = "${data.archive_file.package_code_for_lambda.output_base64sha256}"
  lambda_iam_role_arn     = "${aws_iam_role.lambda_config_sqs_to_snow_role.arn}"
  lambda_iam_role_id      = "${aws_iam_role.lambda_config_sqs_to_snow_role.id}"

  providers = {
    aws = "aws.ap-northeast-1"
  }
}

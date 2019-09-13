resource "aws_lambda_function" "lambda_config_sqs_to_snow" {
  filename         = "/tmp/tf-lambda/lambda-sns-to-snow.zip"
  function_name    = "lambda_config_sqs_to_snow"
  description      = "Takes AWS Config to SQS input and pushes it to ServiceNow"
  role             = "${var.lambda_iam_role_arn}"
  handler          = "aws-config-sns-to-snow.lambda_handler_sqs"
  source_code_hash = "${var.lambda_source_code_hash}"
  runtime          = "python3.6"
  timeout          = 900
  memory_size      = 1024

  environment {
    variables = {
      # SNOW_HOSTNAME = "${var.snow_hostname}"
      # SNOW_USER     = "${var.snow_user}"
      # SNOW_PASSWORD = "${var.snow_password}"
      SNOW_SECRET   = "${var.snow_secret}"
    }
  }
}

resource "aws_cloudwatch_log_group" "cwl_lambda_sqs_to_snow" {
  name = "/aws/lambda/lambda_config_sqs_to_snow"

  # TODO: Eric Elnicki:
  #retention_in_days  = ...
  tags {
    Name    = "Lambda AWS Config SQS to SNOW log"
    Comment = "Created by Account deployment Terraform of Cloud Architecture team"

    # TODO: Eric Elnicki: what should I use here?...
    #CostCenter  = "${var.cost_center}"
    #POC         = "${var.poc_team_email}"
  }
}

# TODO: move to generic one without region overhead
#  arn:aws:logs:*:.....:log-group:/aws/lambda/lambda_config_sqs_to_snow:*
resource "aws_iam_role_policy" "lambda_log" {
  name = "lambda_sqs_to_snow_log_policy_${var.this_aws_region}"
  role = "${var.lambda_iam_role_id}"

  policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": {
        "Effect": "Allow",
        "Action": [
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:PutLogEvents"
        ],
        "Resource": "${aws_cloudwatch_log_group.cwl_lambda_sqs_to_snow.arn}"
    }
}
EOF
}

#
# SQS part
#
resource "aws_sqs_queue" "aws_config_queue" {
  name                       = "aws-config-to-snow-queue"
  # 30 seconds longer as lambda max time
  visibility_timeout_seconds = 930
  # 1209600 = 14 days, max possible
  message_retention_seconds  = 1209600
  # TODO: maybe tweak to 0?
  receive_wait_time_seconds  = 5
}

data "aws_iam_policy_document" "allow_sns_sendmessage" {

  statement {
    effect    = "Allow"
    actions   = ["SQS:SendMessage"]
    resources = ["${aws_sqs_queue.aws_config_queue.arn}"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    # TODO: fix condition
    #condition {
      #test     = "ForAnyValue:ArnLike"
      #variable = "aws:SourceArn"
      #values   = ["${local.sns_topics}"]
    #}
  }
}

resource "aws_sqs_queue_policy" "allow_sns_to_send_to_sqs" {
  queue_url = "${aws_sqs_queue.aws_config_queue.id}"
  policy    = "${data.aws_iam_policy_document.allow_sns_sendmessage.json}"
}

resource "aws_lambda_event_source_mapping" "sqs_to_lambda_mapping" {
  event_source_arn = "${aws_sqs_queue.aws_config_queue.arn}"
  function_name    = "${aws_lambda_function.lambda_config_sqs_to_snow.arn}"
}

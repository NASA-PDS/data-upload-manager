# Terraform module for the Data Upload Manager (DUM) Status Service SQS Queue

resource "aws_sqs_queue" "status_queue" {
  name                       = "nucleus-dum-status-queue"
  delay_seconds              = 10
  visibility_timeout_seconds = 60
  max_message_size           = 262144
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 0

  tags = var.tags
}

data "aws_iam_policy_document" "status_queue_policy" {
  statement {
    sid    = ""
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }

    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage"
    ]

    resources = [
      aws_sqs_queue.status_queue.arn
    ]
  }
}

resource "aws_sqs_queue_policy" "status_queue_policy" {
  queue_url = aws_sqs_queue.status_queue.id
  policy    = data.aws_iam_policy_document.status_queue_policy.json
}

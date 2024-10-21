#!/bin/bash
set -x
awslocal iam create-role --role-name pds-nucleus-dum-lambda-api-gateway --assume-role-policy-document file://pds-nucleus-dum-lambda-api-gateway-policy.json
awslocal iam create-role --role-name pds-nucleus-dum-lambda-ingress --assume-role-policy-document file://pds-nucleus-dum-lambda-ingress-policy.json
awslocal iam create-role --role-name pds-nucleus-dum-lambda-authorizer --assume-role-policy-document file://pds-nucleus-dum-lambda-authorizer-policy.json

# Authorizer Function for use with the DUM API Gateway

This is a token-based authorizer function to allow only JWT access tokens issued for the client IDs of the Unity Cognito
user pool.

The version was adapted for the DUM from the sample version provided by Unity, found [here](https://github.com/unity-sds/unity-cs-security/tree/main/code_samples/api-gateway-common-lambda-authorizer-function).

The JWT access token is verified using the [aws-jwt-verify](https://github.com/awslabs/aws-jwt-verify) JavaScript library developed by the AWS Labs .

This authorizer can be used to verify JWT access tokens issued for multiple client IDs, presented as a
comma separated list. It is possible to support the verification of JWTs issued by multiple user pools also, as explained in [Trusting multiple User Pools](https://github.com/awslabs/aws-jwt-verify#trusting-multiple-user-pools).

### Steps to use this lambda authorizer function:

1. Execute the following command to get the npm modules (make sure that you have [npm setup](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) in your computer before this step)

```shell
npm install
```

2. Create a deployment package as a ZIP file.

```shell
zip -r dum-lambda-auth.zip .
```

3. Create a lambda function on AWS as explained in https://docs.aws.amazon.com/lambda/latest/dg/getting-started.html

4. Deploy the previously created ZIP file as explained in https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-package.html#gettingstarted-package-zip

5. After deploying the lambda function, go to the lambda function in AWS Console and  click on Configuration -> Environment variables.

6. Configure the following 2 environment variables
   * COGNITO_USER_POOL_ID = <COGNITO_USER_POOL_ID>
   * COGNITO_CLIENT_ID_LIST = <COMMA_SEPERATED_LIST_OF_CLIENT_IDS>

After above steps, the lambda functions can be used in API Gateway Authorizers.

/**
 * Request-based lambda authorizer function to allow only JWT access tokens issued for the user pool
 * configured as lambda environment variable COGNITO_USER_POOL_ID and the list of
 * client ids configured as lambda environment variable COGNITO_CLIENT_ID_LIST.
 *
 * Note: Please make sure to configure COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID_LIST
 * environment variable for this lambda.
 *
 */

/**
 * Verifies a JWT token and checks requested group against the Cognito groups of the decoded token.
 * The requested group must be among the Cognito groups for the authenticated use to authorize the
 * incoming request.
 *
 * The JWT access token is verified using the aws-jwt-verify JavaScript library developed by AWS Labs.
 *
 * References:
 * https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html
 * https://auth0.com/docs/secure/tokens/json-web-tokens/validate-json-web-tokens
 * https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html
 * https://github.com/awslabs/aws-jwt-verify
 *
 */
exports.handler = async(event, _context, callback) => {
    let token = event.headers.Authorization;
    let accessToken;

    if (token.startsWith("Bearer")) {
        accessToken = token.split(' ')[1];
    } else {
        console.log("Token not valid! Does not start with Bearer.");
        callback("Unauthorized");
    }

    // Use the aws-jwt-verify
    const { CognitoJwtVerifier } = require("aws-jwt-verify");

    // Create a verifier that expects valid access tokens from COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID_LIST
    const verifier = CognitoJwtVerifier.create({
        userPoolId: process.env.COGNITO_USER_POOL_ID,
        tokenUse: "access",
        clientId: process.env.COGNITO_CLIENT_ID_LIST.split(',').map(item=>item.trim()),
    });

    // Conduct verification
    try {
        const payload = await verifier.verify(accessToken);
        console.log("Token is valid. Payload:", payload);
    } catch (error) {
        console.log("Token not valid!");
        console.log(error);
        callback("Unauthorized");
    }

    // Check user groups
    let decoded;

    try {
        decoded = parseJwt(token);

    } catch (error) {
        console.log(error);
        callback("Unauthorized");
    }

    let groups = decoded['cognito:groups'];

    let request_group = event.headers.UserGroup;

    if (groups.includes(request_group)) {
        console.log("VALID TOKEN, ALLOW!!");
        callback(null, generatePolicy('user', 'Allow', event.methodArn));
    } else {
        console.log("Invalid request group, denying access.")
        callback("Unauthorized");
    }

};


/**
 * Parses a JWT token.
 */
function parseJwt (token) {
    let base64Url = token.split('.')[1];
    let base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    let jsonPayload = decodeURIComponent(decode(base64).split('').map(function(c) {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));

    return JSON.parse(jsonPayload);
}


/**
 * Decodes a base 64 encoded string.
 */
function decode(base64Encoded) {
    let converted = Buffer.from(base64Encoded, 'base64').toString()
    return converted;
}

/**
 * Helper function to generate an IAM policy.
 */
let generatePolicy = function(principalId, effect, resource) {
    let authResponse = {};

    authResponse.principalId = principalId;

    if (effect && resource) {
        var policyDocument = {};
        policyDocument.Version = '2012-10-17';
        policyDocument.Statement = [];
        var statementOne = {};
        statementOne.Action = 'execute-api:Invoke';
        statementOne.Effect = effect;
        statementOne.Resource = resource;
        policyDocument.Statement[0] = statementOne;
        authResponse.policyDocument = policyDocument;
    }

    return authResponse;
};

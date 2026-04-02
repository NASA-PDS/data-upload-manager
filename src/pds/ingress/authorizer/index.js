/**
 * Request-based lambda authorizer function to allow only JWT access tokens issued for the user pool
 * configured as lambda environment variable COGNITO_USER_POOL_ID and the list of
 * client ids configured as lambda environment variable COGNITO_CLIENT_ID_LIST.
 */

exports.handler = async(event, _context, callback) => {
    // 1. Handle API Gateway case-sensitivity for headers
    let token = event.headers.Authorization || event.headers.authorization;
    let request_group = event.headers.UserGroup || event.headers.usergroup;

    if (!token || !token.toLowerCase().startsWith("bearer ")) {
        console.log("Token not valid! Missing or does not start with Bearer.");
        callback("Unauthorized");
        return;
    }

    let accessToken = token.split(' ')[1];

    // Use the aws-jwt-verify
    const { CognitoJwtVerifier } = require("aws-jwt-verify");

    const verifier = CognitoJwtVerifier.create({
        userPoolId: process.env.COGNITO_USER_POOL_ID,
        tokenUse: "access",
        clientId: process.env.COGNITO_CLIENT_ID_LIST.split(',').map(item=>item.trim()),
    });

    // Conduct verification (skip for localstack installations)
    if(!(process.env.LOCALSTACK_CONTEXT == "true")) {
        try {
            const payload = await verifier.verify(accessToken);
            console.log("Token is valid. Payload:", payload);
        } catch (error) {
            console.log("Token not valid!", error);
            callback("Unauthorized");
            return;
        }
    } else {
        console.log("Localstack context is enabled, skipping aws-jwt-verify usage")
    }

    // Check user groups
    let decoded;
    try {
        decoded = parseJwt(token);
    } catch (error) {
        console.log("Failed to parse JWT:", error);
        callback("Unauthorized");
        return;
    }

    // 2. Prevent crashes if the user has no groups assigned in Cognito
    let groups = decoded['cognito:groups'] || [];

    // 3. Prevent crashes if the client forgot to send the UserGroup header
    if (!request_group) {
        console.log("Missing UserGroup header in request.");
        callback("Unauthorized");
        return;
    }

    if (groups.includes(request_group)) {
        console.log("VALID TOKEN, ALLOW!!");
        callback(null, generatePolicy('user', 'Allow', event.methodArn));
    } else {
        console.log(`Invalid request group. User belongs to: [${groups}], but requested: ${request_group}`);
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

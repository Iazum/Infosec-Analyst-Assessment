
## Objective
Demonstrate secure API architecture, AI guardrails, application security testing, SIEM monitoring and incident response

## Environment
Cloud: AWS
Region: us-east-1
Deployment: AWS Management Console
Data: Synthetic test data only


# Section 1A: Architecture Design & Description

Architecture description
Overview: 

The organization needs a single, hardened entry  point for all API traffic and a controlled path for sending data to Enterprise LLMs. The design delievrs both on AWS using managed services

  Inbound: every request passes through AWS WAF before reaching Amazon PI Gateway, where it is authenticated, validated, and throttled, then handled by Lambda functions that persis data in DynamoDB
  
  Outbound AI: Lambda functions run in private subnets with no internet route. 
                Calls to the LLM go through a dedicated LLM gateway layer and then to Amazon BEdrock over VPC interface endpoint, so prompts and responses never traverse the public internet
                
  Cross-cutting: KMS encryption, Sectes Manager, least-privilege IAM, and centralized logging ( CloudWatch, CloudTrail)


The design follows three principles: deny by default, defense in depth (multiple independet control layers) and centralized control points ( one gateway in, one gateway out)


INBOUND REQUEST FLOW

Client: Sends and HTTPS request with a JWT (Authorization header) and API key

AWS WAF: Web ACL attached to the API Gateway stage inspects the request. AWS Managed Rules(Core, Known Bad inputs, IP reputation) and a rate based rule block malicious or abusive traffic with a 403 before it reaches the API

API Gateway (REST) : Validates the request against the method's schema (400 if invalid) checks the API key against the usage plan

Cognito: Verifies the JWT signature, issurer, expiry, and audience against the Cognito User Pool. Missingor invlid tokens receive 401

Lambda (in VPC): An authorized request invokes the function under a least-privilege execution role

DynamoDB: Lambda reads or writes through a VPC gateway endpoint, so traffic stays  on the AWS network. Data is encrypted at rest with KMS


Every step emits logs: WAF logs, API Gatewar access logs, Lambda logs

REST API and not HTTP API is used as AWS WAF can be associated directly with REST API stages


OUTBOUND AI REQUEST FLOW

Summarize API Lambda: Receives an authorized request and forwards the text to the LLM gateway layer

LLM gateway layer: Central control point for all AI traffic.. It applies inut validatoin, and size limits, PII redaction, model seclection and prompt logging

Secrets Manager: Holds any third party LLM credentials. Retreived at runtime through a VPC interface endpoint 

Bedrock VPC interface endpoint: Private connection to Amazon BEdrock with private DNS enabled

Amazon Bedrock: Runs the foundation model


Egress Control: The private subnets have no NAT gateway and no route  to an Internet gateway. The lambda security group permits only outbound TCP 443 to the endpoint security group and the DynamoDB prefix list

NETWORK DESIGN

VPC: 10.0.0.0/16, DNS hostnames and resolution enabled

Subnets: 2 private subnets across 2 availability zones

Internet access None

Gateway Endpoint: DynamoDB 

Interface endpoints

Security groups

Data Layer

  DynamoDB with on demand capacity, encryption ate rest using KMS
  
  Access only through Lambda execution role
  
  No direct public access: reachable via gateway endpoint
  
  Sensitive data in transut and rest and encrypted


Design Decisions

| Decision |               Recommended Choice   |                     Reason to state |
| --- | --- | --- |
| API type              |  REST API  |                                  WAF attaches directly to REST stages |
| Auth                | Cognito User Pool  |                         Managed, OIDC compliance, no custom code |
| Database                  | DynamoDB(KMS encrypted) |                    Serverless, IAM controlled, reachable through vpc endpoint |
| Compute                  | Lambda in private subnet |                   No public exposure, no servers to patch |
| LLM                       | Amazon Bedrock (via VPC endpoint) |          Traffic never leaves AWS network |
| Outbound proxy            | Dedicated LLM gateway layer |                 Central place for redaction, loggin, quotas and key custody |

Phase 0
1. Signining in and picking  a region (us-east-1)
2. Billing alarm: 

Phase 1: Design Decisions
| Decision               |   Recommended Choice                      |    Reason to state |
| --- | --- | --- |
| API type         |         REST API      |                              WAF attaches directly to REST stages |
| Auth              |        Cognito User Pool |                           Managed, OIDC compliance, no custom code |
| Database          |        DynamoDB(KMS encrypted)                  |   Serverless, IAM controlled, reachable through vpc endpoint |
| Compute          |         Lambda in private subnet                  |  No public exposure, no servers to patch
|  LLM            |           Amazon Bedrock (via VPC endpoint)        |   Traffic never leaves AWS network |
| Outbound proxy |           Dedicated LLM gateway layer               |  Central place for redaction, loggin, quotas and key custody |


Phase 2: Building the network foundation

Step 1: Create the VPC

Console → VPC → Create VPC → Choose VPC and more

  Name: sec-gw
  IPv4 CIDR: 10.0.0.0/16
  Availability Zones: 2
  Private subnets: 2
  NAT Gateway: None
  VPC endpoints: S3 Gateway
  DNS options: enable DNS hostnames, and enable DNS resolution


Step 2: Add the DynamoDB gateway endpoint

VPC → Endpoints → Create endpoint

  Service: com.amazonaws.<us-east-1>.dynamodb (type Gateway)
  VPC: sec-gw-vpc
  Route tables: both private route tables

This lets a lambda in a private subnet reach DynamoDB without   NAT

Step 3: Create the security groups
VPC → Security groups → Create

| Name |                   Inbound    |                        Outbound |
| --- | --- | --- |
| sec-gw-lambda-sg            | none             |               TCP 443 to sec-gw-endpoint-sg, plus TCP 443 to the DynamoDB prefix list |
| sec-gw-endpoint-sg      | TCP 443 from sec-gw-lambda-sg  |    default |


The DynamoDB prefix list appears in the destination dropdown as the gateway endpoint exists


Step 4: Create the interface endpoints

VPC → Endpoints → Create endpoint (type Interface), once for each
  .com.amazonaws.<us-east-1>.bedrock-runtime
  .com.amazonaws.<us-east-1>.secretsmanager
  .com.amazonaws.<us-east-1>.logs
  .com.amazonaws.<us-east-1>.lambda

For each, both private subnets are selected, sec-gw-endpoint-sg is attached and private DNS name is enabled


Step 5: Check Bedrock access
Console → Amazon Bedrock → model catalog




Part 1b IMPLEMENTATION PLAN
Step 1 DYNAMODB TABLES

Console → DynamoDB → Create table ( two tables with on demand capacity)

| Table |        Partition Key    |  Sort Key        |    Purpose |
| --- | --- | --- |
| Orders    |   userId(String)   |  OrderID (string)   | Orders API data |
| LlmUsage  |   userId (string)  |  day (String)     |   Per user daily AI quota counters |


For both tables, KMS encryption is enabled as AWS managed key. On Orders table, Point in time recovery is enabled


Step 2: IAM Roles (least privilege)

Console → IAM → Roles → Create role → AWS services service → Lambda
3 roles are created
AWS Managed policy,  AWS LambdaVPCAcessExecutionRole is attached to each (they provide loggin and VPC network interface permissions


Step 3 LAMBDA FUNCTIONS

Console → Lambda → Create function → Author from scratch, Python3.12 3 functions are created with their codes

| Function       |     Code file                 |                Role             |         Timeout    |    Environment variables |
| --- | --- | --- | --- | --- | 
| sec-gw-orders    |   apis/orders/lambda_function.py   |         sec-gw-orders-role    |      10s      |    TABLE_NAME=Orders |
| sec-gw-llm-gateway   | apis/llm_gateway/lambda_function.py    |  sec-gw-llm-gateway-role  |    20s        |  USAGE_TABLE=LlmUsage, DAILY_LIMIT=20, MODEL_ID=zai.glm-5.3, MOCK_LLM=false |
| sec-gw-summarize |   apis/summarize/lambda_function.py    |    sec-gw-summarize-role    |    25s       |   LLM_GATEWAY_FUNCTION=sec-gw-llm-gateway |

Bedrock model: a text model is picked (zai.glm-5.3) and a quick test is done

Step 4: COGNITO USER POOL

Console → Cognito → Create user pool 

  Sign in identifier: Email
  
  Password policy: Cognito defaults (min 8, mixed character types)
  MFA: 
  Self registration: Disabled( admin creates users)
  
  App client: Public client, no client secret, name sec-gw-client
  
  Authentication flows: ALLOW_USER_PASSWORD_AUTH and ALLOW_REFRESH_TOKEN_AUTH (enabled)
  
  Token expiry: ID /access token 60 minutes



Step 5: API GATEWAY (REST API)

Console → API Gateway → Create API → REST API (not private) → name sec-gw-api, endpoint type REGIONAL

Authorizer. Authorizers → Create authrozer: type Cognito, user pool is selected, token source Authorization. (Test with Id token to confirm it validates)

Request validators and models (Create validator name body-validator)

Resources and methods. Resource tree below is created with matching function and Method request set: Authorization = Cognito authorizer, API Key required = true


| Resource  |           Method   |   Lambda  |          Model |
| --- | --- | --- |  --- | 
| /orders       |       GET      |   sec-gw-orders   |   none |
| /orders        |      POST     |   sec-gw-orders   |   OrderInput |
| /orders/{orderId}   | GET      |   sec-gw-orders   |   none |
| /ai/summarize       |  POST    |    sec-gw-summarize  |  SummarizeInput |

CORS is not enabled

Account Level Loggin ROle. (API Gateway → Settings → Set a cloudwatch log role ARN (an IAM role with AmazonAPIGatewayPushToClourWatchLogs)

Deploy: Deploy API → new stage prod, INstage detials → Logs and tracing; Access Logging is enabled and CLoudWatch execution logs: Errors only and X Ray tracing


Stage 6: USAGE PLAN AND API KEY

API Gateway → Usage plans → create usage plan sec-gw-standard

  Throttling: rate 2 req/s, burst 5
  Quota: 1000 requests per day
  Associate the sec-gw-api / prod stage
  API keys → Create API ley demo-client-key and added to the plan


Stage 7 : AWS WAF

Console → WAF & Shield → Web ACLs → Create a Web ACL

  Resource type: Regional, same reqion as the API
  
  Associate to sec-gw-api → stage prod
  
  Default action: Allow
  
  Rules ( as below)

 | Priority    |  Rule              |                    Notes |
 | --- | --- | --- |
 | 0        |      RateLimitPerIp(rate based        |    Limits 100 per 5 minutes, aggregate by source IP, actino BLOCK |
 | 1        |    AWSManagedRulesAmazonIPReputationList | Block known bad sources |
 | 2        |    AWSManagedRulesCommonRuleSet          |  XSS, bad bots, size limits |
 | 3        |    AWSManagedRulesKnownBadInputsRuleSet   | Log4j and similar |
 | 4       |     AWSManagedRulesSQLiRuleSet              | SQL injection |


Step 8: Private LLM path check

  The following are working correctly
  Interface endpoints bedrock-runtime and lambda exist woth private DNS enabled, in both private subnets using sec-gw-endpoint-
  
  DynamoDB gateway endpoint is attached to both private route tables
  private route tables have no 0.0.0.0/0


Step 9: Observability and alarms  

  Logs: API Gateway access logs, WAF logs, and the three Lambda log groups (retention to 14 days)
  
  Alarms (CLoudwatch → Alarms), each notifying an SNS email topic
  
      API Gateway 5XXError > o to 5 minutes
      WAF BlockedRequests > 20 for 5 minutes
      Lambda Errors on sec-gw-llm-gateway
  CloudTrail: default event history to record management events


Steps 10: Test, capture evidence, 

1. run_tests.sh is uploaded to cloud shell
2. the bash script is run and results recorded

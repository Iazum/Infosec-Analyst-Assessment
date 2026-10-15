
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





PART C : SAMPLE APIS

| API | Method and path | Backend | Auth |
| --- | --- | --- | --- | 
| Orders | POST / orders | sec-gw-orders → DynamoDB Orders | JWT + API KEy |
| Orders | GET / orders, GET /orders/{orderId} | sec-gw-orders → DynamoDB Orders | JWT + API KEy
| AI summarize | POST /ai/summarize | 	sec-gw-summarize → sec-gw-llm-gateway → Bedrock | JWT + APT Key

What each API demonstrates
  Orders: authenticated CRUD with per user data isolation (userId comes from verified JWT, never from client input), JSON schema request validation, and least priviliege DynamoDB access
  AI summarize: the outbound AI pattern from the architecture: input limits, PII redaction, per user dailty quota (HTTP 429), metadata pnly audit loggin, private connectivity tp Bedrock, and prompt injection aware system prompt


PART D: RATE LIMITING, AUTHENTICATION AND SECURE DATA HANDLING

API rate limiting

Reason for rate limiting

It protectes availability ( abuse, scraping) cost (every LLM call and Lambda invocation is billed) and security (brute force and credential stuffing attempts)


Design Rationale
  Ip based limits (WAF) catch unauthenticated abuse, but since IPs are shared, the limits guards against floods
  
  Key based limits (usage plan) identify the calling application. They give predictable fair use between client teams and the ability to revoke or tier a single client without affecting others
  
  User based limits ( LLM gateway) per person controls
  
  Token bucket behavior: API gateway allows short bursts up to the burst size and then enforces steady ready


Authentication and authorization strategies

Principles
1. Authenticate every request

2. Use the right mechanism for each kind of caller

3. Authorize on the server, using verified identity only

API keys are not authenticated since thery are shared secrets with no user identity, no expiry by default and are easily leaked in logs or repos

How JWT flow works

1. The user signs in against COgnito and receives an ID token, access token, and refresh token

2. The client sends the token in the Authorization header

3. The cognito authorizer validates the signature against the pool's public key, the issuer, the expiry and the token use

4. The verified clains (including sub) are passwd to Lambda in the request context

5. The orders API uses sub as the partition key, so a user can only ever quesry their own records preventing  brocken object level authorization, the top item in  the OWASP API security Top 10)

Token and session hygiene

Short lived access token (60 minutes)
MFA
Self  registration is disabled so acounts are created by an administrator
Passwords handled only by Cognito
Tokens are never logged


Secure data handling

Data in transit

  TLS 1.2 or higher for all client traffic (API Gateway enforces HTTPS
  Traffic from Lambda to DynamoDB and BEdrock travels over VPC endpoints, on the AWS network
  Private subnets have no internet route 


Data at rest
  DynamoDB encrypted with KMS, point in time recovery enabled on Orders
  CloudWatch Logs, secrets and any S3 log buckets encrypted with KMS


Secrets Management

  No secrets in source code, environment variabled or repository
  Secrets Manager stores any third party credentials with automatic rotation
  Bedrock needs no API key: acess is through Lambda's IAM role, which removes a whole class of leaked credntial risk
  The test script  reads credentials from environment variables and published output is redacted

PART E: HOW TO CONFIGURE API GATEWAY/ PROXY TO ENFORCE AI INPUT/OUTPUT GUARDRAILS

Decision: 

API Gateway and WAF handle structure, identity, and volume. The LLM gateway is the single policy enforcement point for AI content, because it is the only component that sees both directions of the conversation

Amazon Bedrock Quardrails provides content filters, sensitive information filters (PII) and denied topics. 

Its ApplyGuardrail API evaluates text independently of any model call, so the same guardrail can screen the input before the model and the output after it and it works for non Bedrock models
CONFIGURATION: PHI DETECTION WITH AMAZON COMPREHEND MEDICAL

Where PHI is a legal concern (for example under HIPAA) a detective detector is added in front of the model

NETWORK LEVEL PHI PROTECTION (defence in depth) Text filters can miss things, so the network design will limit what can leave
  Private subnets with no internet route
  VPC  endpoint policies limiting which Bedrock actions and resources



MAKING THE QUARDRAIL NON BYPASSABLE

1. Single path: only the gateway Lambda's role is allowed to call model APIs
2. Enforcement of  Guardrail use in IAM: Bedrock supports an IAM condition key that can require a specific guardrail on model invocations, so code change that skips guardrail is denied by AWS itself
3. Service control policy at the organization level, denies model invocation from any role except the gateway role
4. Network: no internet route from the application tier so a rogue process cannot call an external model API directly
5. Version pinning: reference a numbered quardrail version and alert on changes through CloudTrail events

Prompt Injection: defence in depth
| Layer | Control | 
| --- | --- |
| Detection | Guardrails prompt attack filter and simple heuristics logged as signals |
| Prompt design | System prompt states that user text is untrusted data; user content is clearly delimited |
| Least privilege | The model only returns text; lacks tools, credentials and ability to call internal APIs, which limits the blast radius of a successful injection |
| Output validation | Output length and format checks, system prompt leakage checks, response filtered before running | 
| Indirect injection | scanning of documents or web content added with the same guardrails and require human confirmation for any action with side effects | 
| Monitoring | Alarms on spikes in blocked prompt attacks per user and feed repeat offenders into stricter throttling | 



TRADEOFFS

Latency: each guradrail calls adds time, so the gateway Lambda timeout and API gateway defauly 29 second integration limit must allow for it

Streaming: output guardrails need the text to inspect, so token by token streaming either waits for chunks to be checked or disabled

Cost: guardrails and comprehend medical are billed per text unit or character

False positives or false negatives: strictness is a business decision, For PHI, blocking is favoured, for general PII, anonymization of users is favoured

Utility vs privacy: anonymizing input can lower answer quality


PART F: TECHNICAL RISKS AND MITIGATION

Risk Register

Likelihood (L), and Impact (I) are rated High / Medium / Low for this architecture

Security risks

| ID | Risks | L | I | Mitigation | Detection | 

| --- | --- | --- | --- | --- | --- |

| S1 | WAF False positives block legitimate traffic | M | M | Roll out Managed rules in count mode first, tune with sampled requests | WAF sampled requests, 403 rate alarm | 
| S2 | WAF bypass or evasion | M | H | Layered controls, body size limits, managed rule updates, defence in depth rather than relying on WAF | Anomaly alarms periodic penetration tests | 
| S3 | Broken object level authorization | M | H | Identity derived partition keys | Automated tests, access pattern loggin | 
| S4 | Credential or token leakage | M | H | No static AWS keys, secrets manager, short token lifetimes, header redaction in logs, rotation of API Keys , secret scanning in repository | Git secret scanning, cloudtrail anomalies |
| S5 | API key misused as authentication | L | M | key only throttling; JWT required for every route | Review of methods settings |
| S6 | Over permissive IAM | M | H | Per function roles scoped to resource ARNS, IAM Access analyzer, periodic permission review | Access Analyzer findings, config rules | 
| S7 | Compromised lambda or dependency | L | H | No internet egress, minimal dependencies, pinned versions | GuardDuty, VPC flow logs |


AI specific risks

| ID | Risks | L | I | Mitigation | Detection | 

| --- | --- | --- | --- | --- | --- |

| A1 | Prompt injection | H | M to H | Guardrail prompt attack filter | Prompt attack metric spikes | 
| A2 | PII/PHI leakage to the model | M | H | Input and output filters, PHI block policy, private endpoints | Guardrails intervention metrics | 
| A3 | Guradrail bypass or drift | L | H | IAM condition enforcing the guardrail | CloudTrail alarms | 
| A4 | Hallucination | H | M | Label output as AI generated keep human review for decisions | User feedback, sampled quality review | 
| A5 | Denial of wallet | M | H | Per user daily quota, throttles, input size cap | Budget and usage alarms | 
| A6 | Vendor or model change | M | M | Model ID in configuration, abstraction in the gateway | Falling regression tests | 
| A7 | Data residency  violation | L to M | H | Pin region, use region specific inference profiles | Config review, CloudTrail | 


Availability and performance risks

| ID | Risks | L | I | Mitigation | Detection | 

| --- | --- | --- | --- | --- | --- |  
| P1 | 	LLM or guardrail latency exceeds API Gateway's 29 s default limit | M | M | Cap input and output sizes, set timeouts below the gateway limit | Latency alarms |
| P2 | 	Bedrock throttling or quota limits | M | M | Request quota increases, retry with exponential backoff and jitter | Throttle metrics | 
| P3 | Fail closed guardrails | M | M | Health alarms retries on transient errors | Error rate alarms | 
| P4 | Lambda in VPC coled starts | M | L | Provisioned concurrency for latency, sensitive routes | Init duration metrics |
| P5 | Single region failure | L | H | Multi region active passive with route 53 failover, DynamoDB global tables | Health checks | 
| P6 | DynamoDB hot partition or throttling | L | M | On demand capacity, well distributed keys | Throttle metrics |
| P7 | Single gateway as bottleneck | L | M | Lambda scales automatically reserved concurrency to protect downstreams | Concurrency metrics | 


Operational and compliance risks

| ID | Risks | L | I | Mitigation | Detection | 

| --- | --- | --- | --- | --- | --- | 
| O1 | Console built infrastructure drifts | H | M | Export to IaC, move to Terraform | Cloudformation drift reports | 
| O2 | Sensitive data in logs | M | H | Metadata only logging, header redaction, log encryption, short retention | Periodic log review | 
| O3 | Alert fatigue | M | M | 	Few high-signal alarms with owners and runbooks | Incident reviews| 
| O4 | Unexpected cost | M | M | Budgets and alarms, tear down demo resources | Billing alarms | 
| O5 | Regulatory exposure | M | H | Data classification, approved use policy | Compliance audits | 
| O6 | Insufficient response | M | H | Written runbooks, ability to disable a user or API key quickly | Game days



Top risks and priority actions
1. Data leakage; highest impact. Prioritize input and output guardrails
2. Authorization and credential failures: Priority of identity driven access, least privilege IAM, and secrets handling
3. Prompt injection; limitation of what a successful injection can do
4. Cost and availability: quotas, budgets, timeouts
5. Operational maturity: Infrastructure as code, runbooks and tested response







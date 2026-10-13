# Architecture Decisions

## Region
us-east-1 (US East — N. Virginia)

## API Layer
Amazon API Gateway REST API protected by AWS WAF

## Application Layer
Two AWS Lambda functions:
1. Employee Directory API
2. Incident Management API

## Identity
Amazon Cognito ar an approved JWT authorizer

## Data Layer
Private database access, least-privilege permissions, and AWS Secrets Manager for credentials

## AI security
An approved outbound AI proxy performs input inspection, sensitive-data checks, output inspection and redaction

## Monitoring
CloudWatch and CloudTrail, Wazuh will be evaluated for centralized security detection and log analysis

## Cost Controls
Avoud idle compute, use synthetic data, set budget alerts, review billing, and delete unused resources

## Known Limitations
The demonstration is not production ready until access controls, loggin, failure handling and security tests have been validated

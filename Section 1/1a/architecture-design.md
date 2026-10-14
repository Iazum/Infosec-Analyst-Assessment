# Section 1.A: Architecture Design & Description

## 1. Overview

This architecture outlines a secure, scalable, and zero-trust-aligned enterprise design deployed on AWS. It integrates edge security, centralized authentication, containerized microservices, isolated data storage, and a secure pipeline for Enterprise AI integration.

## 2. Architecture Diagram



## 3. Edge Security and Ingress

**Traffic flow: Clients → AWS WAF → Amazon API Gateway**

- **Clients:** External or internal applications initiate traffic toward the organization's endpoints.
- **AWS WAF:** Inspects incoming HTTP/HTTPS traffic using managed rule groups and rate-based rules. It helps protect against common web vulnerabilities, including SQL injection and cross-site scripting. AWS Shield provides additional protection against distributed denial-of-service (DDoS) attacks.
- **Amazon API Gateway:** Acts as the entry point for backend services. It manages routing, request validation, throttling and the enforcement of API access policies.

## 4. Authentication and Authorization

**Traffic flow: API Gateway → Amazon Cognito**

Amazon Cognito provides identity management and authentication. Clients obtain tokens through supported OAuth 2.0/OpenID Connect flows and present valid JWTs when accessing protected APIs.

API Gateway authorizers validate the tokens before allowing requests to reach backend services. Application-level authorization checks ensure that users can access only the resources and operations permitted by their roles.

## 5. Private Network Transit and Application Layer

**Traffic flow: API Gateway → VPC Link → Network Load Balancer → ECS Fargate APIs**

- **VPC Link and Network Load Balancer:** Provide private connectivity from API Gateway to backend services running inside the VPC. The services are not directly exposed to the public internet.
- **Amazon ECS with AWS Fargate:** Runs containerized microservices without requiring the organization to manage the underlying container hosts.

Two sample APIs will be deployed:

1. **Employee Directory API:** Returns synthetic employee records to authorized users.
2. **Incident Management API:** Creates and retrieves simulated security incidents for authorized analysts.

The services will use least-privilege IAM roles, controlled network access, secure configuration and centralized logging.

## 6. Data Persistence Layer

**Traffic flow: ECS Fargate APIs → Amazon RDS**

Amazon RDS provides managed relational database storage in private database subnets.

Database access is restricted through security groups so that only authorized application tasks can establish database connections. Database credentials are stored in AWS Secrets Manager rather than embedded in source code or container images.

Encryption at rest and in transit, database auditing, backups and appropriate retention policies will be configured according to the selected database engine and assessment requirements.

## 7. Secure Enterprise AI Pipeline

**Traffic flow: Application APIs → AI Gateway → Bedrock Guardrails → Approved AI model**

The AI gateway acts as an intermediary between internal applications and approved Enterprise LLM services.

### Input guardrails

- Detect and reject or flag potential prompt-injection attempts.
- Inspect prompts for personally identifiable information (PII) and protected health information (PHI).
- Block prohibited sensitive information before it leaves the organization's controlled environment.
- Apply organizational AI-use policies and record security-relevant events.

### Model connectivity

Approved requests are sent to Amazon Bedrock. An interface VPC endpoint powered by AWS PrivateLink can provide private connectivity to supported Bedrock services, subject to the configured endpoint, DNS, routing and access policies.

### Output guardrails

- Inspect model responses for sensitive information.
- Redact PII where appropriate.
- Block responses that violate organizational policies.
- Log policy decisions without unnecessarily retaining sensitive prompts or responses.

Amazon Bedrock Guardrails will provide supported prompt-attack detection, sensitive-information filtering and content controls. The AI proxy will enforce any additional organization-specific checks and output-redaction requirements.

AI requests must pass through the approved proxy and must not be allowed to bypass the guardrails.

## 8. Monitoring and Secrets Management

- **AWS Secrets Manager:** Protects database credentials and other application secrets.
- **Amazon CloudWatch:** Collects application logs, API metrics and operational monitoring data.
- **AWS CloudTrail:** Records supported AWS account activity for auditing and investigation.
- **Amazon GuardDuty and AWS Security Hub:** Can provide threat detection and centralized security findings, subject to service configuration and availability.

Security events will be reviewed and correlated to support incident investigation, access monitoring and compliance reporting.

## 9. Key Security Controls

The proposed architecture applies defense in depth through:

- Web application protection and rate limiting.
- Centralized authentication and application-level authorization.
- Private application and database networking.
- Least-privilege IAM roles and database permissions.
- Encryption in transit and at rest.
- Centralized logging, auditing and security monitoring.
- AI input/output guardrails and sensitive-data inspection.
- Secrets management and controlled outbound AI connectivity.

## 10. Implementation Validation

The implementation will be validated through tests covering authenticated API access, unauthorized requests, rate limiting, WAF rule enforcement, database access restrictions, AI prompt-injection detection, sensitive-data blocking and output redaction.

The results, configuration screenshots and relevant logs will be documented as evidence for the assessment.

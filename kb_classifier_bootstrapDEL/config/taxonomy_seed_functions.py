"""Functional branch of the hand-written seed taxonomy (8 L1 nodes).

Corporate / cross-functional L1s required by the original task, expanded per
02_DESIGN_NOTES.md B.3. Two things are deliberate here:

1. ``Technology & Engineering`` is expanded far beyond the brief's two L2s
   (9 L2 / ~35 L3). The bootstrap corpus is ~95% technical content from an AI
   inference platform (see 01_STATUS.md 3.2); with only two L2s under it, tens
   of thousands of documents would pile into two nodes, depressing every L3
   similarity and distorting the L3 threshold. A detailed technical branch keeps
   the score distribution meaningful.

2. ``Product Management`` is added as an L1 that the brief did not list. The
   brief explicitly permits adding branches based on the actual corpus, and the
   corpus has substantial product/design content (linear/product-management,
   confluence/product-docs, slack/product, slack/design). It is still marked
   ``source: "seed"`` (it is hand-written), and its origin as a skeleton
   extension is noted in bootstrap_report.md. Delete this block to revert to the
   brief's exact L1 list; nothing else depends on it.

Every ``desc`` is a descriptive sentence carrying the vocabulary expected in a
matching document, not a restatement of the node name.
"""

from __future__ import annotations

from ._node import node

FUNCTION_SEED = {
    # -------------------------------------------------------------------
    "corporate_finance_accounting": node(
        "Corporate Finance & Accounting",
        "The company's own finance and accounting function, covering financial "
        "reporting, tax and treasury operations, planning and performance, and "
        "accounts payable and receivable.",
        {
            "financial_reporting": node(
                "Financial Reporting",
                "Preparing the company's financial statements and management "
                "reporting under applicable accounting standards.",
                {
                    "month_end_close_consolidation": node(
                        "Month-End Close & Consolidation",
                        "Period-end close and group consolidation, covering journal "
                        "entries, intercompany eliminations, reconciliations and the "
                        "close calendar."),
                    "statutory_external_reporting": node(
                        "Statutory & External Reporting",
                        "Statutory and external financial reporting, covering annual "
                        "accounts, GAAP and IFRS disclosures, audit support and "
                        "regulatory filings."),
                    "management_reporting_mi": node(
                        "Management Reporting & MI",
                        "Internal management reporting and management information, "
                        "covering monthly management accounts, KPI dashboards, variance "
                        "analysis and board reporting packs."),
                    "accounting_policy_standards": node(
                        "Accounting Policy & Standards",
                        "Accounting policy and standards, covering revenue and lease "
                        "accounting policy, technical accounting positions and "
                        "adoption of new accounting standards."),
                },
            ),
            "tax_treasury_operations": node(
                "Tax & Treasury Operations",
                "Corporate tax compliance and internal treasury operations for the "
                "company itself.",
                {
                    "direct_indirect_tax_compliance": node(
                        "Direct & Indirect Tax Compliance",
                        "Corporate tax compliance, covering corporate income tax, VAT "
                        "and sales tax, tax returns, withholding tax and tax provisioning."),
                    "transfer_pricing": node(
                        "Transfer Pricing",
                        "Transfer pricing between group entities, covering intercompany "
                        "pricing policy, documentation, arm's-length analysis and "
                        "cross-border tax allocation."),
                    "internal_funding_intercompany": node(
                        "Internal Funding & Intercompany",
                        "Internal funding and intercompany treasury, covering "
                        "intercompany loans, cash pooling across entities, internal "
                        "interest and group liquidity."),
                },
            ),
            "planning_performance": node(
                "Planning & Performance",
                "Financial planning and performance management, covering budgeting, "
                "cost analysis and revenue recognition.",
                {
                    "budgeting_forecasting": node(
                        "Budgeting & Forecasting",
                        "Budgeting and forecasting, covering annual budgets, rolling "
                        "forecasts, scenario planning and financial models."),
                    "cost_allocation_unit_economics": node(
                        "Cost Allocation & Unit Economics",
                        "Cost allocation and unit economics, covering cost centres, "
                        "cloud and infrastructure cost attribution, margin analysis and "
                        "cost-per-unit metrics."),
                    "revenue_recognition_billing": node(
                        "Revenue Recognition & Billing",
                        "Revenue recognition and billing, covering usage-based billing, "
                        "subscription revenue, deferred revenue and invoicing of "
                        "customers."),
                },
            ),
            "accounts_payable_receivable": node(
                "Accounts Payable & Receivable",
                "Processing what the company owes and is owed, covering payables, "
                "expenses and receivables.",
                {
                    "invoice_processing_payables": node(
                        "Invoice Processing & Payables",
                        "Supplier invoice processing and accounts payable, covering "
                        "invoice approval, three-way matching, payment runs and vendor "
                        "statement reconciliation."),
                    "expense_management_reimbursement": node(
                        "Expense Management & Reimbursement",
                        "Employee expenses and reimbursement, covering expense policy, "
                        "corporate cards, claim approval and travel-expense processing."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "human_resources": node(
        "Human Resources",
        "The people function covering recruitment, compensation and benefits, "
        "employee relations and workforce operations.",
        {
            "recruitment": node(
                "Recruitment",
                "Hiring talent into the company, covering sourcing, interviewing, "
                "offers and new-hire onboarding.",
                {
                    "sourcing_candidate_pipeline": node(
                        "Sourcing & Candidate Pipeline",
                        "Sourcing candidates and managing the hiring pipeline, covering "
                        "job requisitions, sourcing channels, applicant tracking and "
                        "candidate screening."),
                    "interviewing_assessment": node(
                        "Interviewing & Assessment",
                        "Interviewing and assessing candidates, covering interview "
                        "loops, structured scorecards, technical assessments and "
                        "interviewer training."),
                    "offers_hiring_decisions": node(
                        "Offers & Hiring Decisions",
                        "Making offers and hiring decisions, covering offer approval, "
                        "compensation packages, background checks and offer negotiation."),
                    "onboarding_new_hire_enablement": node(
                        "Onboarding & New Hire Enablement",
                        "Onboarding and enabling new hires, covering first-day setup, "
                        "orientation, provisioning access and ramp-up plans for new "
                        "employees."),
                },
            ),
            "compensation_benefits": node(
                "Compensation & Benefits",
                "Rewarding employees through pay, equity, benefits and payroll.",
                {
                    "salary_structure_pay_review": node(
                        "Salary Structure & Pay Review",
                        "Salary structure and pay review, covering pay bands, "
                        "benchmarking, annual salary review cycles and merit increases."),
                    "equity_incentive_plans": node(
                        "Equity & Incentive Plans",
                        "Equity and incentive plans, covering stock options and RSUs, "
                        "vesting schedules, bonus plans and long-term incentives."),
                    "health_insurance_wellbeing_benefits": node(
                        "Health, Insurance & Wellbeing Benefits",
                        "Health, insurance and wellbeing benefits, covering medical and "
                        "dental cover, life and disability insurance, wellbeing "
                        "programmes and benefits enrolment."),
                    "leave_time_off_policy": node(
                        "Leave & Time-Off Policy",
                        "Leave and time-off policy, covering annual leave, sick leave, "
                        "parental leave, sabbaticals and public holidays."),
                    "payroll_operations": node(
                        "Payroll Operations",
                        "Payroll operations, covering payroll runs, tax and social "
                        "deductions, payslips, off-cycle payments and payroll "
                        "reconciliation."),
                },
            ),
            "employee_relations": node(
                "Employee Relations",
                "Managing the employee lifecycle beyond pay, covering performance, "
                "career, learning, conduct and culture.",
                {
                    "performance_management_reviews": node(
                        "Performance Management & Reviews",
                        "Performance management, covering goal setting, performance "
                        "reviews, ratings calibration and performance-improvement plans."),
                    "career_framework_promotion": node(
                        "Career Framework & Promotion",
                        "Career framework and promotion, covering career ladders, "
                        "levelling, promotion cases and role expectations."),
                    "learning_development": node(
                        "Learning & Development",
                        "Learning and development, covering training programmes, skills "
                        "development, mentoring, certifications and learning platforms."),
                    "conduct_grievance_disciplinary": node(
                        "Conduct, Grievance & Disciplinary",
                        "Conduct, grievance and disciplinary matters, covering code of "
                        "conduct, investigations, disciplinary process and grievance "
                        "resolution."),
                    "workplace_culture_engagement": node(
                        "Workplace Culture & Engagement",
                        "Workplace culture and engagement, covering engagement surveys, "
                        "diversity and inclusion, recognition and team events."),
                },
            ),
            "workforce_operations": node(
                "Workforce Operations",
                "The operational backbone of HR, covering systems, planning and "
                "offboarding.",
                {
                    "hr_systems_employee_data": node(
                        "HR Systems & Employee Data",
                        "HR systems and employee data, covering HRIS platforms, "
                        "employee records, data changes and HR reporting."),
                    "workforce_planning_headcount": node(
                        "Workforce Planning & Headcount",
                        "Workforce planning and headcount, covering headcount budgets, "
                        "org design, hiring plans and capacity planning."),
                    "offboarding_exit": node(
                        "Offboarding & Exit",
                        "Offboarding and exit, covering resignations, exit interviews, "
                        "access revocation, final pay and knowledge handover."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "legal": node(
        "Legal",
        "The legal function covering contracts, corporate governance, disputes and "
        "intellectual property.",
        {
            "contract_management": node(
                "Contract Management",
                "Drafting, reviewing and managing contracts across the company's "
                "commercial relationships.",
                {
                    "customer_contracts_msas": node(
                        "Customer Contracts & MSAs",
                        "Customer contracts, covering master service agreements, order "
                        "forms, data-processing addenda, SLAs and contract negotiation "
                        "with customers."),
                    "contract_templates_playbooks": node(
                        "Contract Templates & Playbooks",
                        "Contract templates and negotiation playbooks, covering standard "
                        "clauses, fallback positions, approval matrices and clause "
                        "libraries."),
                    "contract_lifecycle_renewals": node(
                        "Contract Lifecycle & Renewals",
                        "Contract lifecycle management, covering signature workflows, "
                        "contract repositories, renewal tracking and expiry management."),
                },
            ),
            "corporate_governance": node(
                "Corporate Governance",
                "Governance of the company as a legal entity, covering the board, "
                "entity management and policy framework.",
                {
                    "board_committee_governance": node(
                        "Board & Committee Governance",
                        "Board and committee governance, covering board meetings, "
                        "minutes, resolutions, committee charters and director duties."),
                    "entity_management_licensing": node(
                        "Entity Management & Licensing",
                        "Corporate entity management and licensing, covering entity "
                        "incorporation, registrations, business licences and statutory "
                        "filings."),
                    "policy_framework_attestation": node(
                        "Policy Framework & Attestation",
                        "Corporate policy framework and attestations, covering policy "
                        "ownership, mandatory policy attestation, code of conduct and "
                        "policy review cycles."),
                },
            ),
            "disputes_regulatory_legal": node(
                "Disputes & Regulatory Legal",
                "Handling disputes and regulatory legal matters affecting the company.",
                {
                    "litigation_dispute_resolution": node(
                        "Litigation & Dispute Resolution",
                        "Litigation and dispute resolution, covering claims, legal "
                        "proceedings, settlements, arbitration and external counsel "
                        "management."),
                    "regulatory_liaison_legal_opinions": node(
                        "Regulatory Liaison & Legal Opinions",
                        "Regulatory liaison and legal opinions, covering regulator "
                        "engagement, legal opinions, compliance advice and interpretation "
                        "of new law."),
                },
            ),
            "intellectual_property": node(
                "Intellectual Property",
                "Protecting and managing the company's intellectual property and "
                "software licensing.",
                {
                    "ip_trademark_management": node(
                        "IP & Trademark Management",
                        "Intellectual property and trademark management, covering "
                        "patents, trademarks, IP assignment, inventor agreements and "
                        "brand protection."),
                    "open_source_licensing": node(
                        "Open Source Licensing",
                        "Open-source licensing, covering license compatibility, "
                        "attribution obligations, open-source review and contribution "
                        "policy."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    # Technology & Engineering -- deliberately the most detailed branch.
    # -------------------------------------------------------------------
    "technology_engineering": node(
        "Technology & Engineering",
        "Building and running the company's software and infrastructure, covering "
        "cloud infrastructure, software development, reliability, security, data "
        "and machine-learning platforms, architecture and IT service management.",
        {
            "infrastructure_operations": node(
                "Infrastructure & Operations",
                "Provisioning and operating the compute, networking and cloud "
                "infrastructure that runs the platform.",
                {
                    "cloud_infrastructure_capacity": node(
                        "Cloud Infrastructure & Capacity",
                        "Cloud infrastructure and capacity, covering cloud accounts and "
                        "regions, virtual machines, storage, capacity planning and cloud "
                        "resource quotas."),
                    "kubernetes_container_platform": node(
                        "Kubernetes & Container Platform",
                        "Kubernetes and container platform, covering clusters, pods and "
                        "deployments, Helm charts, autoscaling, ingress and container "
                        "orchestration."),
                    "networking_connectivity": node(
                        "Networking & Connectivity",
                        "Networking and connectivity, covering VPCs and subnets, load "
                        "balancers, DNS, VPNs, service mesh and network routing."),
                    "compute_gpu_fleet_management": node(
                        "Compute & GPU Fleet Management",
                        "Compute and GPU fleet management, covering GPU nodes and "
                        "accelerators, scheduling and bin-packing, device drivers, "
                        "utilization and fleet health for inference workloads."),
                    "infrastructure_as_code_provisioning": node(
                        "Infrastructure as Code & Provisioning",
                        "Infrastructure as code and provisioning, covering Terraform, "
                        "declarative provisioning, environment bootstrapping and "
                        "configuration management."),
                    "cost_capacity_optimization": node(
                        "Cost & Capacity Optimization",
                        "Infrastructure cost and capacity optimization, covering cloud "
                        "spend, rightsizing, reserved and spot capacity, GPU utilization "
                        "efficiency and cost monitoring."),
                },
            ),
            "software_development": node(
                "Software Development",
                "Writing and shipping application and platform software, covering "
                "services, SDKs, engineering standards, CI/CD and tooling.",
                {
                    "service_api_development": node(
                        "Service & API Development",
                        "Service and API development, covering backend services, REST "
                        "and gRPC APIs, request handling, service contracts and "
                        "microservice design."),
                    "sdks_client_libraries": node(
                        "SDKs & Client Libraries",
                        "SDKs and client libraries, covering language SDKs, client "
                        "library design, versioning, packaging and integration "
                        "examples."),
                    "code_review_engineering_standards": node(
                        "Code Review & Engineering Standards",
                        "Code review and engineering standards, covering pull-request "
                        "review, coding conventions, style guides, linting and code "
                        "quality gates."),
                    "build_cicd_release_engineering": node(
                        "Build, CI/CD & Release Engineering",
                        "Build, CI/CD and release engineering, covering build pipelines, "
                        "continuous integration, automated deployment, release trains "
                        "and artifact management."),
                    "developer_tooling_local_environment": node(
                        "Developer Tooling & Local Environment",
                        "Developer tooling and local environments, covering local dev "
                        "setup, dev containers, CLIs, code generators and internal "
                        "developer tools."),
                    "technical_documentation_examples": node(
                        "Technical Documentation & Examples",
                        "Technical documentation and examples, covering API reference "
                        "docs, quickstarts, tutorials, code samples and the docs site."),
                },
            ),
            "site_reliability_observability": node(
                "Site Reliability & Observability",
                "Keeping the platform reliable and observable, covering monitoring, "
                "logging, alerting, incidents, SLOs and performance testing.",
                {
                    "monitoring_metrics_dashboards": node(
                        "Monitoring, Metrics & Dashboards",
                        "Monitoring, metrics and dashboards, covering Prometheus and "
                        "Grafana, service metrics, golden signals and dashboard "
                        "definitions."),
                    "logging_tracing": node(
                        "Logging & Tracing",
                        "Logging and distributed tracing, covering structured logs, log "
                        "aggregation, trace spans, correlation IDs and request tracing."),
                    "alerting_on_call_rotation": node(
                        "Alerting & On-Call Rotation",
                        "Alerting and on-call rotation, covering alert rules, paging, "
                        "on-call schedules, escalation policies and alert fatigue."),
                    "incident_response_postmortems": node(
                        "Incident Response & Postmortems",
                        "Incident response and postmortems, covering incident command, "
                        "severity levels, mitigation, root-cause analysis and blameless "
                        "postmortem write-ups."),
                    "slo_sli_error_budgets": node(
                        "SLO, SLI & Error Budgets",
                        "Service-level objectives and error budgets, covering SLIs, SLO "
                        "targets, error-budget policy, burn-rate alerts and reliability "
                        "reporting."),
                    "performance_load_testing": node(
                        "Performance & Load Testing",
                        "Performance and load testing, covering benchmarks, latency and "
                        "throughput testing, stress tests, load generation and "
                        "regression of performance."),
                },
            ),
            "information_security": node(
                "Information Security",
                "Securing the platform and its data, covering identity, encryption, "
                "vulnerability management, threat detection and security review.",
                {
                    "identity_authentication_access_control": node(
                        "Identity, Authentication & Access Control",
                        "Identity, authentication and access control, covering SSO and "
                        "OAuth, MFA, role-based access, least privilege and access "
                        "reviews."),
                    "encryption_key_management": node(
                        "Encryption & Key Management",
                        "Encryption and key management, covering data-at-rest and "
                        "in-transit encryption, key management services, secrets "
                        "management and certificate rotation."),
                    "vulnerability_patch_management": node(
                        "Vulnerability & Patch Management",
                        "Vulnerability and patch management, covering vulnerability "
                        "scanning, dependency CVEs, patch cadence and remediation "
                        "tracking."),
                    "security_monitoring_threat_detection": node(
                        "Security Monitoring & Threat Detection",
                        "Security monitoring and threat detection, covering SIEM, "
                        "intrusion detection, anomaly alerts, security incident response "
                        "and threat intelligence."),
                    "security_review_threat_modelling": node(
                        "Security Review & Threat Modelling",
                        "Security review and threat modelling, covering design security "
                        "reviews, threat models, penetration testing and secure "
                        "development practices."),
                    "audit_logging_evidence": node(
                        "Audit Logging & Evidence",
                        "Audit logging and compliance evidence, covering audit trails, "
                        "tamper-evident logs, SOC 2 evidence collection and access "
                        "audit reports."),
                },
            ),
            "data_analytics_platform": node(
                "Data & Analytics Platform",
                "The data platform powering analytics, covering pipelines, warehousing, "
                "BI and data quality.",
                {
                    "data_pipelines_etl": node(
                        "Data Pipelines & ETL",
                        "Data pipelines and ETL, covering batch and streaming ingestion, "
                        "transformation jobs, orchestration with Airflow and pipeline "
                        "scheduling."),
                    "data_warehouse_modelling": node(
                        "Data Warehouse & Modelling",
                        "Data warehouse and modelling, covering warehouse schemas, dbt "
                        "models, dimensional modelling, partitioning and query "
                        "performance."),
                    "bi_dashboards_reporting_tools": node(
                        "BI, Dashboards & Reporting Tools",
                        "Business intelligence and reporting tools, covering BI "
                        "dashboards, self-service analytics, report building and metric "
                        "definitions."),
                    "data_quality_lineage": node(
                        "Data Quality & Lineage",
                        "Data quality and lineage, covering data validation, freshness "
                        "and completeness checks, lineage tracking and data contracts."),
                },
            ),
            "ai_ml_platform": node(
                "AI & Machine Learning Platform",
                "The platform for serving, evaluating and optimizing machine-learning "
                "models, central to this company's inference product.",
                {
                    "model_serving_inference_runtime": node(
                        "Model Serving & Inference Runtime",
                        "Model serving and inference runtime, covering inference servers, "
                        "request batching, KV cache, token streaming, GPU inference and "
                        "serving latency."),
                    "model_registry_lifecycle": node(
                        "Model Registry & Lifecycle",
                        "Model registry and lifecycle, covering model versioning, model "
                        "onboarding, promotion between environments and model "
                        "deprecation."),
                    "model_evaluation_benchmarking": node(
                        "Model Evaluation & Benchmarking",
                        "Model evaluation and benchmarking, covering eval harnesses, "
                        "prompt sets, quality metrics, regression triage and benchmark "
                        "datasets."),
                    "prompt_retrieval_engineering": node(
                        "Prompt & Retrieval Engineering",
                        "Prompt and retrieval engineering, covering prompt templates, "
                        "retrieval-augmented generation, embeddings, vector search and "
                        "context construction."),
                    "model_optimization_quantization": node(
                        "Model Optimization & Quantization",
                        "Model optimization and quantization, covering quantization "
                        "profiles, distillation, kernel optimization, throughput tuning "
                        "and accuracy trade-offs."),
                    "ml_experimentation_feature_rollout": node(
                        "ML Experimentation & Feature Rollout",
                        "ML experimentation and rollout, covering A/B experiments, "
                        "feature flags for models, canary rollout and experiment health "
                        "dashboards."),
                },
            ),
            "architecture_technical_standards": node(
                "Architecture & Technical Standards",
                "Setting technical direction and standards, covering decision records, "
                "API design standards and architecture reviews.",
                {
                    "architecture_decision_records": node(
                        "Architecture Decision Records",
                        "Architecture decision records, covering ADRs, design rationale, "
                        "trade-off analysis and decision history for technical choices."),
                    "api_design_standards": node(
                        "API Design Standards",
                        "API design standards, covering REST conventions, versioning "
                        "policy, error models, pagination and API consistency "
                        "guidelines."),
                    "platform_architecture_design_reviews": node(
                        "Platform Architecture & Design Reviews",
                        "Platform architecture and design reviews, covering system "
                        "design documents, architecture review boards, scalability "
                        "design and reference architectures."),
                },
            ),
            "quality_engineering": node(
                "Quality Engineering",
                "Assuring software quality, covering test automation, test "
                "environments and defect triage.",
                {
                    "test_automation_coverage": node(
                        "Test Automation & Coverage",
                        "Test automation and coverage, covering unit and integration "
                        "tests, end-to-end automation, test frameworks and coverage "
                        "targets."),
                    "test_environments_data": node(
                        "Test Environments & Data",
                        "Test environments and data, covering staging environments, test "
                        "data management, environment provisioning and service mocking."),
                    "defect_triage_regression": node(
                        "Defect Triage & Regression",
                        "Defect triage and regression, covering bug triage, severity "
                        "classification, regression testing and release quality gates."),
                },
            ),
            "it_service_management": node(
                "IT Service Management",
                "Running IT services and operations, covering change management, "
                "service desk, access requests and deployments.",
                {
                    "change_release_management": node(
                        "Change & Release Management",
                        "Change and release management, covering change requests, "
                        "approval workflows, release windows, change advisory and "
                        "rollback plans."),
                    "service_desk_support_requests": node(
                        "Service Desk & Support Requests",
                        "Service desk and support requests, covering internal ticketing, "
                        "IT help desk, request fulfilment and SLA on internal support."),
                    "access_requests_provisioning": node(
                        "Access Requests & Provisioning",
                        "Access requests and provisioning, covering account creation, "
                        "role assignment, joiner-mover-leaver workflows and access "
                        "approval."),
                    "deployment_environment_operations": node(
                        "Deployment & Environment Operations",
                        "Deployment and environment operations, covering production "
                        "deploys, environment configuration, feature toggles and "
                        "operational runbooks."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "sales_marketing": node(
        "Sales & Marketing",
        "Winning and growing customers, covering brand and communications, customer "
        "acquisition, product marketing and customer success.",
        {
            "brand_communications": node(
                "Brand & Communications",
                "Brand and communications, covering brand assets, public relations, "
                "internal communications and events.",
                {
                    "brand_creative_assets": node(
                        "Brand & Creative Assets",
                        "Brand and creative assets, covering brand guidelines, logos and "
                        "visual identity, creative production and asset libraries."),
                    "public_relations_media": node(
                        "Public Relations & Media",
                        "Public relations and media, covering press releases, media "
                        "relations, analyst relations and external announcements."),
                    "internal_communications_all_hands": node(
                        "Internal Communications & All-Hands",
                        "Internal communications, covering company all-hands, "
                        "announcements, newsletters and leadership updates to staff."),
                    "events_conferences": node(
                        "Events & Conferences",
                        "Events and conferences, covering trade shows, webinars, "
                        "sponsorships, event logistics and speaker management."),
                },
            ),
            "customer_acquisition": node(
                "Customer Acquisition",
                "Generating and closing new business, covering demand generation, "
                "sales pipeline, pricing and competitive intelligence.",
                {
                    "lead_generation_demand_gen": node(
                        "Lead Generation & Demand Gen",
                        "Lead generation and demand generation, covering campaigns, "
                        "inbound and outbound leads, marketing funnels and lead scoring."),
                    "sales_pipeline_deal_management": node(
                        "Sales Pipeline & Deal Management",
                        "Sales pipeline and deal management, covering CRM opportunities, "
                        "deal stages, forecasting and sales-cycle progression."),
                    "pricing_quotes_proposals": node(
                        "Pricing, Quotes & Proposals",
                        "Pricing, quotes and proposals, covering price books, discount "
                        "approvals, quotes, RFP responses and proposal writing."),
                    "competitive_market_intelligence": node(
                        "Competitive & Market Intelligence",
                        "Competitive and market intelligence, covering competitor "
                        "analysis, battlecards, market sizing and win-loss analysis."),
                },
            ),
            "product_marketing": node(
                "Product Marketing",
                "Bringing products to market, covering positioning, launch and content.",
                {
                    "positioning_messaging": node(
                        "Positioning & Messaging",
                        "Positioning and messaging, covering value propositions, "
                        "messaging frameworks, target personas and differentiation."),
                    "launch_go_to_market": node(
                        "Launch & Go-to-Market",
                        "Launch and go-to-market, covering launch plans, release "
                        "marketing, enablement of sales and go-to-market strategy."),
                    "content_thought_leadership": node(
                        "Content & Thought Leadership",
                        "Content and thought leadership, covering blog posts, whitepapers, "
                        "case studies, webinars and thought-leadership articles."),
                },
            ),
            "customer_success_support": node(
                "Customer Success & Support",
                "Retaining and growing customers post-sale, covering onboarding, account "
                "health, support and renewals.",
                {
                    "customer_onboarding_adoption": node(
                        "Customer Onboarding & Adoption",
                        "Customer onboarding and adoption, covering implementation, "
                        "integration guides, enablement and driving product adoption."),
                    "account_health_qbr": node(
                        "Account Health & QBR",
                        "Account health and quarterly business reviews, covering health "
                        "scores, usage reviews, success plans and QBR decks."),
                    "support_case_handling_escalation": node(
                        "Support Case Handling & Escalation",
                        "Support case handling and escalation, covering support tickets, "
                        "escalation playbooks, known issues and workarounds and case "
                        "resolution."),
                    "renewals_churn_expansion": node(
                        "Renewals, Churn & Expansion",
                        "Renewals, churn and expansion, covering renewal management, "
                        "churn risk, upsell and cross-sell and expansion revenue."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "procurement_vendor_management": node(
        "Procurement & Vendor Management",
        "Sourcing and managing suppliers and third parties, covering vendor "
        "contracts, purchasing and third-party risk.",
        {
            "vendor_contracts": node(
                "Vendor Contracts",
                "Managing supplier contracts and performance, covering selection, "
                "negotiation and SLA management.",
                {
                    "vendor_selection_rfp": node(
                        "Vendor Selection & RFP",
                        "Vendor selection and RFP, covering requests for proposal, "
                        "vendor evaluation, scoring criteria and supplier shortlisting."),
                    "vendor_contract_negotiation": node(
                        "Vendor Contract Negotiation",
                        "Vendor contract negotiation, covering commercial terms, pricing, "
                        "liability and data-protection clauses in supplier agreements."),
                    "vendor_performance_sla_management": node(
                        "Vendor Performance & SLA Management",
                        "Vendor performance and SLA management, covering service-level "
                        "monitoring, vendor scorecards, reviews and remediation of "
                        "underperformance."),
                },
            ),
            "sourcing_purchasing": node(
                "Sourcing & Purchasing",
                "Day-to-day purchasing and licensing, covering requisitions, purchase "
                "orders and software licensing.",
                {
                    "purchase_requisition_po": node(
                        "Purchase Requisition & PO",
                        "Purchase requisition and purchase orders, covering requisition "
                        "approval, PO creation, goods receipt and procurement workflow."),
                    "software_cloud_licensing": node(
                        "Software & Cloud Licensing",
                        "Software and cloud licensing, covering SaaS subscriptions, "
                        "license true-ups, seat management and cloud commitment "
                        "agreements."),
                },
            ),
            "third_party_risk_due_diligence": node(
                "Third-Party Risk & Due Diligence",
                "Assessing and onboarding third parties from a risk perspective.",
                {
                    "vendor_security_compliance_review": node(
                        "Vendor Security & Compliance Review",
                        "Vendor security and compliance review, covering security "
                        "questionnaires, SOC 2 review, data-processing assessment and "
                        "vendor risk rating."),
                    "vendor_onboarding_offboarding": node(
                        "Vendor Onboarding & Offboarding",
                        "Vendor onboarding and offboarding, covering supplier setup, "
                        "access provisioning, data return and termination of vendor "
                        "relationships."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "facilities_administration": node(
        "Facilities & Administration",
        "Running the workplace and administrative operations, covering office "
        "operations and health, safety and environment.",
        {
            "office_operations": node(
                "Office Operations",
                "Running offices and workplace services, covering facilities, physical "
                "security, travel and assets.",
                {
                    "workplace_office_services": node(
                        "Workplace & Office Services",
                        "Workplace and office services, covering office space, seating, "
                        "catering, cleaning, mail and reception services."),
                    "physical_security_access": node(
                        "Physical Security & Access",
                        "Physical security and access, covering badge access, visitor "
                        "management, CCTV, alarm systems and building security."),
                    "travel_expense_administration": node(
                        "Travel & Expense Administration",
                        "Travel and expense administration, covering travel booking, "
                        "travel policy, corporate travel agents and expense processing."),
                    "equipment_asset_management": node(
                        "Equipment & Asset Management",
                        "Equipment and asset management, covering laptops and hardware "
                        "issuance, asset tracking, inventory and equipment returns."),
                },
            ),
            "health_safety_environment": node(
                "Health, Safety & Environment",
                "Workplace health, safety and sustainability.",
                {
                    "workplace_health_safety": node(
                        "Workplace Health & Safety",
                        "Workplace health and safety, covering risk assessments, "
                        "incident reporting, first aid, fire safety and ergonomics."),
                    "sustainability_environmental": node(
                        "Sustainability & Environmental",
                        "Sustainability and environmental programmes, covering carbon "
                        "footprint, energy use, recycling and ESG reporting."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    # Product Management -- skeleton extension (not in the brief's L1 list).
    # -------------------------------------------------------------------
    "product_management": node(
        "Product Management",
        "Defining what to build and why, covering product strategy and roadmap, "
        "product analytics and experimentation, and product design and UX. Added "
        "as a seed L1 because the corpus has substantial product and design "
        "content that would otherwise pollute the technology branch.",
        {
            "product_strategy_roadmap": node(
                "Product Strategy & Roadmap",
                "Product strategy and roadmap, covering prioritization, requirements "
                "and discovery.",
                {
                    "roadmap_prioritization": node(
                        "Roadmap & Prioritization",
                        "Roadmap and prioritization, covering product roadmaps, "
                        "prioritization frameworks, backlog grooming and quarterly "
                        "planning."),
                    "product_requirements_specs": node(
                        "Product Requirements & Specs",
                        "Product requirements and specs, covering PRDs, user stories, "
                        "acceptance criteria and feature specifications."),
                    "product_discovery_research": node(
                        "Product Discovery & Research",
                        "Product discovery and research, covering customer interviews, "
                        "problem validation, opportunity assessment and discovery "
                        "experiments."),
                },
            ),
            "product_analytics_experimentation": node(
                "Product Analytics & Experimentation",
                "Measuring product usage and running experiments to inform decisions.",
                {
                    "usage_metrics_adoption_analysis": node(
                        "Usage Metrics & Adoption Analysis",
                        "Usage metrics and adoption analysis, covering product "
                        "analytics, funnels, retention cohorts and feature-adoption "
                        "tracking."),
                    "ab_testing_experiments": node(
                        "A/B Testing & Experiments",
                        "A/B testing and experiments, covering experiment design, "
                        "hypothesis testing, statistical significance and rollout "
                        "decisions."),
                },
            ),
            "product_design_ux": node(
                "Product Design & UX",
                "Designing the product experience, covering UX research and design "
                "systems.",
                {
                    "ux_research_usability": node(
                        "UX Research & Usability",
                        "UX research and usability, covering usability testing, user "
                        "research, journey mapping and interaction design feedback."),
                    "design_system_ui_patterns": node(
                        "Design System & UI Patterns",
                        "Design system and UI patterns, covering component libraries, "
                        "design tokens, UI guidelines and reusable interface patterns."),
                },
            ),
        },
    ),
}

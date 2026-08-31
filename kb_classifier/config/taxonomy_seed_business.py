"""Business-line branch of the hand-written seed taxonomy (9 L1 nodes).

This is the banking business-line skeleton required verbatim by the original
task (00_ORIGINAL_TASK.md), expanded with additional L2/L3 nodes per the design
in 02_DESIGN_NOTES.md B.2.

Every ``desc`` is a full descriptive sentence, not a label. The desc is the text
bge-m3 actually embeds and compares against documents, so each one deliberately
spells out the vocabulary expected in a matching article -- vocabulary coverage
here is recall downstream. Descs never merely restate the node name.

NOTE ON CORPUS MISMATCH (see 01_STATUS.md 3.2): the bootstrap corpus is the
internal knowledge base of an AI-inference platform company, not a bank. These
banking L1s are expected to attract almost no documents; they are written to
spec regardless, and the mismatch is reported in bootstrap_report.md.
"""

from __future__ import annotations

from ._node import node

BUSINESS_SEED = {
    # -------------------------------------------------------------------
    "retail_banking": node(
        "Retail Banking",
        "Products and services sold to individual consumers through branches and "
        "digital channels, covering everyday deposit accounts, personal borrowing, "
        "personal cards, and the branch and contact-centre operations that serve them.",
        {
            "deposit_accounts": node(
                "Deposit Accounts",
                "Personal savings, current and checking accounts including account "
                "opening, interest accrual, statements, overdraft handling, dormancy "
                "and closure for individual customers.",
                {
                    "savings_accounts": node(
                        "Savings Accounts",
                        "Interest-bearing personal savings and time-deposit products, "
                        "covering rate tiers, term deposits, certificates of deposit, "
                        "notice accounts and maturity rollover."),
                    "current_checking_accounts": node(
                        "Current & Checking Accounts",
                        "Everyday transactional current and checking accounts, including "
                        "debit access, direct debits, standing orders, overdraft limits "
                        "and account fees for individual customers."),
                    "account_opening_kyc_onboarding": node(
                        "Account Opening & KYC Onboarding",
                        "Retail customer account opening and identity verification, "
                        "covering KYC document collection, sanctions and PEP checks, "
                        "digital onboarding journeys and first-account funding."),
                    "account_servicing_maintenance": node(
                        "Account Servicing & Maintenance",
                        "Ongoing servicing of retail deposit accounts such as address "
                        "and mandate changes, statement requests, standing-order edits, "
                        "dormant-account handling and account closure."),
                },
            ),
            "consumer_lending": node(
                "Consumer Lending",
                "Borrowing products for individual consumers including mortgages, auto "
                "finance, personal loans and their servicing and collections.",
                {
                    "mortgage_lending": node(
                        "Mortgage Lending",
                        "Residential mortgage origination and refinancing, covering "
                        "affordability assessment, property valuation, loan-to-value "
                        "limits, fixed and variable rates, and completion."),
                    "auto_loans": node(
                        "Auto Loans",
                        "Vehicle and auto finance for individuals, including hire "
                        "purchase, personal contract plans, dealer financing and "
                        "balloon-payment structures."),
                    "personal_unsecured_loans": node(
                        "Personal & Unsecured Loans",
                        "Unsecured personal instalment loans and lines of credit, "
                        "covering application, affordability checks, pricing by risk "
                        "grade and early-repayment handling."),
                    "loan_servicing_collections": node(
                        "Loan Servicing & Collections",
                        "Servicing of consumer loans after drawdown, covering "
                        "repayment schedules, arrears management, hardship forbearance, "
                        "collections and recoveries on delinquent accounts."),
                },
            ),
            "retail_cards": node(
                "Retail Cards",
                "Personal credit, debit and prepaid card products, their issuance, "
                "rewards and dispute handling for individual cardholders.",
                {
                    "credit_card_issuance": node(
                        "Credit Card Issuance",
                        "Issuing personal credit cards, covering application and credit "
                        "limits, interest and fees, statements, balance transfers and "
                        "card activation and reissue."),
                    "debit_prepaid_cards": node(
                        "Debit & Prepaid Cards",
                        "Personal debit and prepaid card products linked to deposit or "
                        "wallet balances, including issuance, top-up, spend controls and "
                        "replacement of lost or stolen cards."),
                    "card_rewards_loyalty": node(
                        "Card Rewards & Loyalty",
                        "Cardholder rewards, cashback, points and loyalty programmes, "
                        "including earn and redemption rules, partner offers and tier "
                        "benefits."),
                    "cardholder_disputes_chargebacks": node(
                        "Cardholder Disputes & Chargebacks",
                        "Handling cardholder transaction disputes and chargebacks, "
                        "covering fraud claims, merchant representment, scheme dispute "
                        "rules and refund processing."),
                },
            ),
            "branch_channel_operations": node(
                "Branch & Channel Operations",
                "Physical and assisted service channels for retail customers, including "
                "branch operations, ATM and self-service networks and contact centres.",
                {
                    "branch_operations": node(
                        "Branch Operations",
                        "Day-to-day running of retail branches, covering teller cash "
                        "handling, vault management, appointment booking, queue "
                        "management and branch compliance controls."),
                    "atm_self_service_network": node(
                        "ATM & Self-Service Network",
                        "Operation of ATMs and self-service kiosks, covering cash "
                        "replenishment, uptime monitoring, deposit automation and "
                        "self-service transaction support."),
                    "contact_centre_operations": node(
                        "Contact Centre Operations",
                        "Telephone and chat contact centres serving retail customers, "
                        "covering call routing, agent scripts, service-level targets, "
                        "authentication and complaint capture."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "corporate_banking": node(
        "Corporate Banking",
        "Banking services for corporate and institutional clients, covering corporate "
        "account management, cash management, and trade services for businesses.",
        {
            "corporate_accounts": node(
                "Corporate Accounts",
                "Opening and managing accounts for corporate entities, including "
                "know-your-business checks, account structures, signing mandates and "
                "ongoing corporate account servicing.",
                {
                    "account_opening_kyb": node(
                        "Account Opening & KYB",
                        "Onboarding corporate customers with know-your-business "
                        "verification, beneficial-ownership checks, entity documentation "
                        "and corporate sanctions screening."),
                    "account_structures_mandates": node(
                        "Account Structures & Mandates",
                        "Designing corporate account hierarchies and signing mandates, "
                        "covering multi-entity structures, authorised signatories, "
                        "delegated approvals and account permissions."),
                    "corporate_account_servicing": node(
                        "Corporate Account Servicing",
                        "Ongoing servicing of corporate accounts including balance and "
                        "statement reporting, fee billing, mandate changes and query "
                        "resolution for business clients."),
                },
            ),
            "cash_management_services": node(
                "Cash Management Services",
                "Corporate cash management covering collections, disbursements, "
                "liquidity structures and integration of banking with client ERP "
                "systems.",
                {
                    "collections_receivables": node(
                        "Collections & Receivables",
                        "Corporate collections and receivables services, covering "
                        "virtual accounts, direct debit collection, lockbox, receivables "
                        "reconciliation and cash application."),
                    "disbursements_payables": node(
                        "Disbursements & Payables",
                        "Corporate payables and disbursement services, covering bulk "
                        "payment files, payroll runs, supplier payments and "
                        "payment approval workflows."),
                    "liquidity_structures_sweeping": node(
                        "Liquidity Structures & Sweeping",
                        "Corporate liquidity structures such as notional pooling, "
                        "physical cash sweeping, interest optimisation and target-balance "
                        "management across group accounts."),
                    "host_to_host_erp_integration": node(
                        "Host-to-Host & ERP Integration",
                        "Connecting corporate treasury and ERP systems to the bank via "
                        "host-to-host file transfer, SWIFT connectivity and API "
                        "integration for payments and reporting."),
                },
            ),
            "trade_services": node(
                "Trade Services",
                "Corporate trade services including documentary collections, guarantees "
                "and supply-chain finance supporting commercial trade.",
                {
                    "documentary_collections": node(
                        "Documentary Collections",
                        "Bank-handled documentary collections for trade, covering "
                        "documents against payment and against acceptance, collecting "
                        "and remitting bank roles and settlement instructions."),
                    "bank_guarantees_standby_lcs": node(
                        "Bank Guarantees & Standby LCs",
                        "Issuing bank guarantees and standby letters of credit, covering "
                        "performance and payment guarantees, bid bonds, wording review "
                        "and claims under guarantee."),
                    "supply_chain_finance": node(
                        "Supply Chain Finance",
                        "Supply-chain and receivables finance programmes, covering "
                        "supplier onboarding, approved-payables finance, invoice "
                        "discounting and buyer-led financing."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "payments": node(
        "Payments",
        "Movement and settlement of funds across payment rails and schemes, covering "
        "payment processing, acquiring gateways, card payments and payment regulation.",
        {
            "payment_processing": node(
                "Payment Processing",
                "Processing and settling account-to-account payments across domestic "
                "and real-time rails, including clearing, reconciliation and exception "
                "handling.",
                {
                    "domestic_transfers_ach": node(
                        "Domestic Transfers & ACH",
                        "Domestic credit transfers and ACH batch payments, covering "
                        "direct debits, standing orders, bulk files, return codes and "
                        "settlement windows."),
                    "real_time_instant_payments": node(
                        "Real-Time & Instant Payments",
                        "Instant and real-time payment schemes offering immediate "
                        "clearing, covering 24x7 availability, request-to-pay, payment "
                        "confirmation and instant-payment limits."),
                    "wire_transfers_rtgs": node(
                        "Wire Transfers & RTGS",
                        "High-value wire transfers and real-time gross settlement, "
                        "covering central-bank RTGS rails, correspondent routing, "
                        "settlement finality and cut-off times."),
                    "payment_clearing_settlement": node(
                        "Payment Clearing & Settlement",
                        "Interbank clearing and settlement of payments, covering net "
                        "settlement cycles, settlement accounts, nostro positions and "
                        "scheme settlement obligations."),
                    "payment_exceptions_reconciliation": node(
                        "Payment Exceptions & Reconciliation",
                        "Handling failed, returned and unmatched payments, covering "
                        "repair queues, investigations, recalls, reconciliation breaks "
                        "and exception reporting."),
                },
            ),
            "payment_gateway": node(
                "Payment Gateway",
                "Merchant-facing payment acquiring and gateway services, covering "
                "onboarding, gateway APIs, tokenization and gateway availability.",
                {
                    "merchant_onboarding_acquiring": node(
                        "Merchant Onboarding & Acquiring",
                        "Onboarding merchants to accept card and digital payments, "
                        "covering underwriting, merchant category codes, settlement "
                        "accounts and acquiring risk checks."),
                    "gateway_apis_integration": node(
                        "Gateway APIs & Integration",
                        "Integrating merchants with the payment gateway via checkout "
                        "APIs, SDKs, hosted payment pages, webhooks and payment-status "
                        "callbacks."),
                    "tokenization_payment_security": node(
                        "Tokenization & Payment Security",
                        "Securing card data through tokenization, PCI-DSS scope "
                        "reduction, encryption of payment credentials and 3-D Secure "
                        "authentication."),
                    "gateway_availability_throughput": node(
                        "Gateway Availability & Throughput",
                        "Operating the payment gateway for high availability and "
                        "throughput, covering transaction capacity, latency, failover "
                        "and peak-load handling."),
                },
            ),
            "card_payments": node(
                "Card Payments",
                "Card-scheme payment flows covering interchange, authorization, "
                "clearing and fraud prevention across card networks.",
                {
                    "card_scheme_rules_interchange": node(
                        "Card Scheme Rules & Interchange",
                        "Card-network scheme rules and interchange economics, covering "
                        "Visa and Mastercard mandates, interchange fees, scheme "
                        "compliance and assessment charges."),
                    "authorization_switching": node(
                        "Authorization & Switching",
                        "Authorising and switching card transactions, covering issuer "
                        "authorization, stand-in processing, routing between acquirer "
                        "and issuer and decline reason codes."),
                    "card_clearing_settlement": node(
                        "Card Clearing & Settlement",
                        "Clearing and settling card transactions between acquirers and "
                        "issuers, covering presentment, settlement files, funding cycles "
                        "and scheme settlement."),
                    "payment_fraud_prevention": node(
                        "Payment Fraud Prevention",
                        "Detecting and preventing card and payment fraud, covering "
                        "transaction scoring, velocity rules, 3-D Secure, chargeback "
                        "mitigation and fraud-ring detection."),
                },
            ),
            "payment_regulation_standards": node(
                "Payment Regulation & Standards",
                "Regulatory and messaging standards governing payments, including "
                "ISO 20022 migration and payment-services regulation.",
                {
                    "iso20022_message_standards": node(
                        "ISO 20022 & Message Standards",
                        "Payment messaging standards and their migration, covering "
                        "ISO 20022 pacs and pain messages, MT-to-MX conversion, "
                        "structured remittance data and message validation."),
                    "payment_services_regulation": node(
                        "Payment Services Regulation",
                        "Regulation of payment services and providers, covering PSD2 and "
                        "open-banking rules, strong customer authentication, e-money "
                        "licensing and safeguarding of funds."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "lending": node(
        "Lending",
        "Commercial and institutional lending, covering corporate loan origination, "
        "credit assessment and ongoing loan-portfolio management.",
        {
            "corporate_lending": node(
                "Corporate Lending",
                "Lending to corporate borrowers, covering syndicated and structured "
                "facilities, working-capital lines and the documentation and covenants "
                "that govern them.",
                {
                    "syndicated_structured_loans": node(
                        "Syndicated & Structured Loans",
                        "Syndicated and structured corporate loans, covering lead "
                        "arranger and participant roles, facility agreements, tranching "
                        "and agency administration."),
                    "working_capital_facilities": node(
                        "Working Capital Facilities",
                        "Short-term working-capital financing, covering revolving credit "
                        "facilities, overdrafts, invoice finance and seasonal borrowing "
                        "for corporates."),
                    "loan_documentation_covenants": node(
                        "Loan Documentation & Covenants",
                        "Corporate loan documentation and covenant management, covering "
                        "term sheets, facility agreements, financial covenants, "
                        "conditions precedent and covenant testing."),
                },
            ),
            "credit_assessment": node(
                "Credit Assessment",
                "Assessing borrower creditworthiness before lending, covering scoring "
                "models, underwriting policy and collateral valuation.",
                {
                    "credit_scoring_models": node(
                        "Credit Scoring Models",
                        "Statistical and judgemental credit scoring, covering "
                        "application and behavioural scorecards, probability-of-default "
                        "models, rating grades and model calibration."),
                    "underwriting_policy_approval": node(
                        "Underwriting Policy & Approval",
                        "Credit underwriting policy and approval, covering lending "
                        "criteria, delegated approval authorities, credit committees and "
                        "exception handling."),
                    "collateral_security_valuation": node(
                        "Collateral & Security Valuation",
                        "Valuing and managing loan collateral, covering security "
                        "registration, haircuts, revaluation, perfection of charges and "
                        "loan-to-value monitoring."),
                },
            ),
            "loan_portfolio_management": node(
                "Loan Portfolio Management",
                "Managing the performance of the lending book after origination, "
                "covering monitoring, early warning and workout of problem loans.",
                {
                    "portfolio_monitoring_early_warning": node(
                        "Portfolio Monitoring & Early Warning",
                        "Monitoring the loan portfolio for deterioration, covering "
                        "early-warning indicators, watchlists, concentration limits and "
                        "portfolio risk reporting."),
                    "non_performing_loans_workout": node(
                        "Non-Performing Loans & Workout",
                        "Managing non-performing and distressed loans, covering "
                        "restructuring, workout strategies, provisioning, recoveries and "
                        "loan write-offs."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "treasury": node(
        "Treasury",
        "Bank treasury function managing the institution's own cash, funding, "
        "liquidity and balance-sheet market risk.",
        {
            "cash_management": node(
                "Cash Management",
                "Managing the bank's own cash positions and intraday funding across "
                "nostro accounts and settlement systems.",
                {
                    "nostro_cash_position_management": node(
                        "Nostro & Cash Position Management",
                        "Managing nostro and vostro balances and daily cash positions, "
                        "covering balance forecasting, funding gaps, reconciliation and "
                        "correspondent-account management."),
                    "intraday_funding_settlement": node(
                        "Intraday Funding & Settlement",
                        "Managing intraday liquidity and settlement, covering payment "
                        "throughput timing, intraday credit lines, collateral at central "
                        "banks and settlement risk."),
                },
            ),
            "liquidity_management": node(
                "Liquidity Management",
                "Managing the bank's liquidity and wholesale funding to meet regulatory "
                "ratios and funding needs.",
                {
                    "liquidity_risk_lcr_nsfr": node(
                        "Liquidity Risk & LCR/NSFR",
                        "Regulatory liquidity risk management, covering the liquidity "
                        "coverage ratio, net stable funding ratio, high-quality liquid "
                        "assets and liquidity stress testing."),
                    "funding_wholesale_borrowing": node(
                        "Funding & Wholesale Borrowing",
                        "Wholesale funding of the bank, covering money-market borrowing, "
                        "repo, certificates of deposit, bond issuance and funding-cost "
                        "management."),
                },
            ),
            "markets_alm": node(
                "Markets & Asset-Liability Management",
                "Managing balance-sheet market risk and the investment portfolio, "
                "covering interest-rate, FX and securities exposures.",
                {
                    "interest_rate_fx_risk": node(
                        "Interest Rate & FX Risk",
                        "Managing interest-rate and foreign-exchange risk on the balance "
                        "sheet, covering duration and gap analysis, hedging with swaps "
                        "and forwards, and repricing risk."),
                    "investment_portfolio_securities": node(
                        "Investment Portfolio & Securities",
                        "Managing the treasury investment portfolio, covering government "
                        "and corporate bond holdings, liquidity buffers, mark-to-market "
                        "and portfolio duration."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "risk_compliance": node(
        "Risk & Compliance",
        "Enterprise risk management and regulatory compliance, covering financial "
        "crime, regulatory reporting, credit and operational risk, data privacy and "
        "fraud.",
        {
            "anti_money_laundering": node(
                "Anti-Money Laundering",
                "Preventing money laundering and terrorist financing, covering "
                "transaction monitoring, sanctions screening, customer due diligence "
                "and suspicious-activity reporting.",
                {
                    "transaction_monitoring_alerts": node(
                        "Transaction Monitoring & Alerts",
                        "Monitoring transactions for money-laundering patterns, covering "
                        "detection scenarios, alert triage, false-positive tuning and "
                        "case investigation."),
                    "sanctions_watchlist_screening": node(
                        "Sanctions & Watchlist Screening",
                        "Screening customers and payments against sanctions and watch "
                        "lists, covering name matching, OFAC and UN lists, real-time "
                        "payment filtering and hit disposition."),
                    "customer_due_diligence_kyc_policy": node(
                        "Customer Due Diligence & KYC Policy",
                        "Customer due diligence policy, covering KYC standards, "
                        "enhanced due diligence for high-risk customers, "
                        "beneficial-ownership identification and periodic review."),
                    "suspicious_activity_reporting": node(
                        "Suspicious Activity Reporting",
                        "Reporting suspicious activity to authorities, covering SAR and "
                        "STR filing, internal escalation, regulatory timelines and "
                        "record keeping."),
                },
            ),
            "regulatory_reporting": node(
                "Regulatory Reporting",
                "Reporting to regulators and managing regulatory change and "
                "examinations across prudential and transaction reporting.",
                {
                    "prudential_capital_reporting": node(
                        "Prudential & Capital Reporting",
                        "Regulatory prudential reporting, covering capital adequacy "
                        "returns, Basel and CRR reporting, risk-weighted assets and "
                        "regulatory capital ratios."),
                    "transaction_trade_reporting": node(
                        "Transaction & Trade Reporting",
                        "Regulatory transaction and trade reporting, covering MiFID and "
                        "EMIR reporting, trade repositories, reporting completeness and "
                        "reconciliation with regulators."),
                    "regulatory_change_management": node(
                        "Regulatory Change Management",
                        "Managing changes in regulation, covering horizon scanning, "
                        "impact assessment, implementation planning and tracking of "
                        "regulatory obligations."),
                    "regulatory_examinations_internal_audit": node(
                        "Regulatory Examinations & Internal Audit",
                        "Regulatory examinations and internal audit, covering examiner "
                        "requests, audit findings, remediation tracking and control "
                        "attestations."),
                },
            ),
            "credit_risk_management": node(
                "Credit Risk Management",
                "Measuring and controlling credit risk across the portfolio, covering "
                "risk models, exposure limits and stress testing.",
                {
                    "credit_risk_models_ifrs9_ecl": node(
                        "Credit Risk Models & IFRS 9 ECL",
                        "Credit-risk models and expected-loss provisioning, covering "
                        "IFRS 9 ECL staging, PD, LGD and EAD estimation and "
                        "impairment calculation."),
                    "credit_limits_exposure_management": node(
                        "Credit Limits & Exposure Management",
                        "Managing credit limits and exposures, covering single-name and "
                        "sector concentration limits, large-exposure rules, limit "
                        "breaches and exposure aggregation."),
                    "stress_testing_capital_adequacy": node(
                        "Stress Testing & Capital Adequacy",
                        "Stress testing and capital adequacy, covering regulatory and "
                        "internal stress scenarios, ICAAP, capital planning and "
                        "reverse stress testing."),
                },
            ),
            "operational_technology_risk": node(
                "Operational & Technology Risk",
                "Managing operational, third-party and technology risk and the control "
                "framework that governs them.",
                {
                    "operational_risk_control_framework": node(
                        "Operational Risk & Control Framework",
                        "Operational risk management framework, covering risk and "
                        "control self-assessment, key risk indicators, loss taxonomy and "
                        "control testing."),
                    "third_party_outsourcing_risk": node(
                        "Third-Party & Outsourcing Risk",
                        "Managing third-party and outsourcing risk, covering vendor risk "
                        "assessment, outsourcing regulation, concentration risk and "
                        "supplier resilience."),
                    "business_continuity_resilience": node(
                        "Business Continuity & Resilience",
                        "Operational resilience and business continuity, covering "
                        "important business services, impact tolerances, disaster "
                        "recovery and continuity testing."),
                    "incident_loss_event_management": node(
                        "Incident & Loss Event Management",
                        "Managing operational incidents and loss events, covering "
                        "incident capture, root-cause analysis, loss data collection and "
                        "regulatory incident reporting."),
                },
            ),
            "data_privacy_protection": node(
                "Data Privacy & Protection",
                "Protecting personal data and managing records in line with privacy "
                "regulation.",
                {
                    "privacy_policy_data_subject_rights": node(
                        "Privacy Policy & Data Subject Rights",
                        "Data-privacy policy and individual rights, covering GDPR "
                        "principles, data-subject access requests, consent management "
                        "and privacy impact assessments."),
                    "data_retention_records_management": node(
                        "Data Retention & Records Management",
                        "Records management and data retention, covering retention "
                        "schedules, archival, legal hold, secure disposal and records "
                        "classification."),
                },
            ),
            "fraud_risk": node(
                "Fraud Risk",
                "Detecting and investigating fraud against the bank and its customers "
                "across channels and products.",
                {
                    "fraud_detection_investigation": node(
                        "Fraud Detection & Investigation",
                        "Detecting and investigating fraud, covering application and "
                        "account-takeover fraud, scam and authorised-push-payment fraud, "
                        "case investigation and victim reimbursement."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "wealth_management": node(
        "Wealth Management",
        "Managing and advising on the wealth of high-net-worth individuals and "
        "investors, covering private banking and investment advisory.",
        {
            "private_banking": node(
                "Private Banking",
                "Banking and wealth services for high-net-worth clients, covering "
                "relationship coverage, discretionary portfolios and estate planning.",
                {
                    "hnw_client_onboarding_coverage": node(
                        "HNW Client Onboarding & Coverage",
                        "Onboarding and covering high-net-worth clients, covering "
                        "source-of-wealth verification, relationship management, "
                        "bespoke pricing and client segmentation."),
                    "discretionary_portfolio_management": node(
                        "Discretionary Portfolio Management",
                        "Managing client portfolios on a discretionary basis, covering "
                        "mandates, asset allocation, rebalancing and portfolio "
                        "performance reporting."),
                    "trust_estate_planning": node(
                        "Trust & Estate Planning",
                        "Trust and estate planning for wealthy clients, covering trusts, "
                        "succession planning, inheritance structuring and wealth "
                        "transfer."),
                },
            ),
            "investment_advisory": node(
                "Investment Advisory",
                "Advising clients on investments and distributing investment products, "
                "covering suitability, research and fund distribution.",
                {
                    "investment_product_suitability": node(
                        "Investment Product Suitability",
                        "Assessing suitability of investment products, covering risk "
                        "profiling, appropriateness tests, product governance and "
                        "advice documentation."),
                    "research_market_commentary": node(
                        "Research & Market Commentary",
                        "Investment research and market commentary, covering asset-class "
                        "outlooks, equity and fixed-income analysis, model portfolios "
                        "and market updates."),
                    "fund_distribution_custody": node(
                        "Fund Distribution & Custody",
                        "Distributing funds and providing custody, covering fund "
                        "platforms, subscription and redemption, safekeeping of assets "
                        "and corporate actions."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "trade_finance": node(
        "Trade Finance",
        "Financing and settling international trade, covering letters of credit, "
        "cross-border settlement and export/import finance.",
        {
            "letters_of_credit": node(
                "Letters of Credit",
                "Documentary letters of credit supporting trade, covering issuance, "
                "document examination and settlement under LC terms.",
                {
                    "lc_issuance_advising": node(
                        "LC Issuance & Advising",
                        "Issuing and advising letters of credit, covering applicant and "
                        "beneficiary roles, issuing and advising banks, UCP 600 terms "
                        "and confirmation."),
                    "document_examination_discrepancies": node(
                        "Document Examination & Discrepancies",
                        "Examining trade documents under letters of credit, covering "
                        "compliance with LC terms, discrepancy identification, waiver "
                        "requests and document rejection."),
                    "lc_amendments_settlement": node(
                        "LC Amendments & Settlement",
                        "Amending and settling letters of credit, covering amendments, "
                        "acceptances, deferred payment, negotiation and reimbursement "
                        "between banks."),
                },
            ),
            "cross_border_settlement": node(
                "Cross-Border Settlement",
                "Settling cross-border payments and remittances, covering correspondent "
                "banking, FX conversion and cross-border compliance.",
                {
                    "correspondent_banking_swift": node(
                        "Correspondent Banking & SWIFT",
                        "Correspondent banking and SWIFT messaging, covering nostro and "
                        "vostro relationships, SWIFT payment messages, relationship "
                        "management and correspondent due diligence."),
                    "fx_conversion_remittance": node(
                        "FX Conversion & Remittance",
                        "Foreign-exchange conversion and remittance, covering cross-"
                        "currency payments, FX rates and spreads, remittance corridors "
                        "and beneficiary payout."),
                    "cross_border_compliance_screening": node(
                        "Cross-Border Compliance & Screening",
                        "Compliance for cross-border flows, covering sanctions screening "
                        "of international payments, correspondent KYC, transparency of "
                        "payment fields and de-risking."),
                },
            ),
            "export_import_finance": node(
                "Export & Import Finance",
                "Financing exporters and importers, covering export credit, receivables "
                "discounting and import trade loans.",
                {
                    "export_credit_receivables_discounting": node(
                        "Export Credit & Receivables Discounting",
                        "Export finance, covering export credit agency cover, forfaiting, "
                        "receivables discounting and pre- and post-shipment finance."),
                    "import_financing_trade_loans": node(
                        "Import Financing & Trade Loans",
                        "Import financing, covering trade loans, import bills, "
                        "shipping guarantees and financing of the purchase and inventory "
                        "cycle."),
                },
            ),
        },
    ),
    # -------------------------------------------------------------------
    "digital_banking": node(
        "Digital Banking",
        "Customer-facing digital banking channels and open ecosystems, covering "
        "mobile banking, open-banking APIs, fintech partnerships and digital "
        "experience.",
        {
            "mobile_banking": node(
                "Mobile Banking",
                "Mobile banking apps and their features, security and release quality "
                "for customers on smartphones.",
                {
                    "mobile_app_features_journeys": node(
                        "Mobile App Features & Journeys",
                        "Mobile banking app features and customer journeys, covering "
                        "balance and transaction views, payments and transfers, "
                        "in-app servicing and notifications."),
                    "mobile_authentication_device_binding": node(
                        "Mobile Authentication & Device Binding",
                        "Mobile authentication and device security, covering biometric "
                        "login, device binding, push-based approvals and secure element "
                        "storage."),
                    "mobile_app_release_quality": node(
                        "Mobile App Release & Quality",
                        "Releasing and assuring mobile app quality, covering app-store "
                        "release, staged rollout, crash monitoring and mobile "
                        "regression testing."),
                },
            ),
            "open_banking_apis": node(
                "Open Banking APIs",
                "Open-banking APIs and the developer and consent ecosystem around them "
                "for third parties.",
                {
                    "api_products_developer_portal": node(
                        "API Products & Developer Portal",
                        "Open-banking API products and developer portal, covering "
                        "account-information and payment-initiation APIs, developer "
                        "onboarding, sandbox and API documentation."),
                    "consent_authorization": node(
                        "Consent & Authorization",
                        "Open-banking consent and authorization, covering consent "
                        "capture, OAuth flows, scope and expiry of consent and consent "
                        "dashboards."),
                    "third_party_provider_management": node(
                        "Third-Party Provider Management",
                        "Managing third-party providers in open banking, covering TPP "
                        "registration, eIDAS certificates, access controls and "
                        "TPP monitoring."),
                },
            ),
            "fintech_partnerships": node(
                "Fintech Partnerships",
                "Partnerships with fintechs to embed banking and integrate partners "
                "into the platform.",
                {
                    "embedded_finance_baas": node(
                        "Embedded Finance & BaaS",
                        "Embedded finance and banking-as-a-service, covering white-label "
                        "accounts and cards, program management, partner ledgers and "
                        "revenue sharing."),
                    "partner_integration_certification": node(
                        "Partner Integration & Certification",
                        "Integrating and certifying fintech partners, covering technical "
                        "onboarding, sandbox testing, certification criteria and "
                        "go-live approval."),
                },
            ),
            "digital_channel_experience": node(
                "Digital Channel Experience",
                "Web and digital banking experience across internet banking, digital "
                "onboarding and conversational assistants.",
                {
                    "internet_banking_platform": node(
                        "Internet Banking Platform",
                        "Internet and online banking platform, covering web login, "
                        "account dashboards, online payments, secure messaging and "
                        "session management."),
                    "digital_onboarding_ekyc": node(
                        "Digital Onboarding & eKYC",
                        "Digital customer onboarding and electronic KYC, covering "
                        "document capture, liveness and selfie checks, identity "
                        "verification and straight-through account opening."),
                    "conversational_ai_assistants": node(
                        "Conversational & AI Assistants",
                        "Conversational banking and AI assistants, covering chatbots, "
                        "virtual assistants, intent recognition and automated customer "
                        "self-service."),
                },
            ),
        },
    ),
}

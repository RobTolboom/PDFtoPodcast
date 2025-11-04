# DRAFT – Commercial Software License Agreement (Self-Hosted)

> **Status:** Draft for legal review. This document is not final and remains subject to change by counsel.

This Commercial Software License Agreement ("Agreement") is between Tolboom Medical ("Licensor") and the customer identified in the Order Form ("Customer"). The Agreement becomes effective on the Effective Date stated in the Order Form.

## 1. Scope and Relationship to PPL
1.1 Software. "Software" means Licensor's PDF-to-report/podcast converter that uses large language models (LLMs), including executables, installers, configuration files, and documentation delivered for self-hosted use.

1.2 Relationship to Prosperity Public License. Noncommercial use and a 30-day commercial trial are governed by the Prosperity Public License 3.0.0 (PPL) found in the repository (`LICENSE`). This Agreement governs Commercial Use beyond the PPL trial. If there is a conflict, this Agreement controls for Commercial Use.

1.3 Commercial Use. Any use by or for an organization or for direct or indirect commercial advantage, including internal business operations.

## 2. License Grant and Permitted Users
2.1 Grant. Subject to payment and compliance, Licensor grants Customer a non-exclusive, non-transferable, non-sublicensable, organization-wide license to install and use the Software on Customer-controlled systems for Commercial Use during the Subscription Term specified in the Order Form.

2.2 Users. Use is limited to Customer employees. Affiliates and contractors are not covered; each organization must obtain its own license.

2.3 Delivery Form. The Software is delivered as executables/binaries (including packaged Python runtimes). No source code is provided under this Agreement.

## 3. Redistribution and Restrictions
3.1 Redistribution under PPL. Customer may externally redistribute unmodified copies of the Software only under the PPL 3.0.0 for noncommercial purposes, preserving all required notices. Customer may not grant commercial rights to third parties; each third party requires its own commercial license for Commercial Use.

3.2 No service offering. Customer may not host, rent, lease, lend, or offer the Software as a service to third parties.

3.3 Competing models. Customer may not use the Software or its outputs to train or improve a model or service that competes with the Software.

3.4 Reverse engineering. Reverse engineering is prohibited except to the limited extent mandated by applicable law.

3.5 Legal compliance. Customer will comply with all applicable laws, including data protection and export regulations.

## 4. Third-Party Providers (Pass-Through)
4.1 Providers. The Software may call third-party LLM providers (currently OpenAI). Customer must comply with all applicable provider terms, including content, safety, export, and use-case restrictions.

4.2 Changes. Licensor may switch or add providers. Customer will not use the Software in a way that causes Licensor or any provider to breach provider terms.

4.3 Suspension. Licensor may suspend use if Customer's use violates provider terms or creates material risk to Licensor or a provider.

## 5. Metrics, Fees, and Fair Use
5.1 Pricing model. As specified in the Order Form: either subscription with fair use, or per-PDF billing.

5.2 Counting unit (per-PDF). A chargeable conversion is a successful run for a unique input identified by the SHA-256 hash of the PDF contents or by DOI, as reported by Customer. Duplicates are not counted.

5.3 Retries and timeouts. Up to two retries per PDF due to failure or timeout are not billable. Jobs exceeding ten minutes of wall-clock time auto-fail and are not billable.

5.4 Fair use (subscription). The Order Form specifies a per-month fair use threshold. Persistent excess for two consecutive months allows Licensor to move Customer to a higher tier or invoice overage at the rate stated in the Order Form.

5.5 Telemetry. The Software does not transmit usage data to Licensor. Customer must maintain internal usage records sufficient to substantiate reported counts.

5.6 Reports. Customer will provide a monthly usage report (CSV or JSON) on request and for any month with variable fees, in the format stated in the Order Form.

## 6. Delivery; System Limits
6.1 Delivery. Delivery is electronic. Customer is responsible for environment prerequisites.

6.2 Limits. The recommended upload limit is 10 MB per PDF by default (matching the Software configuration). Provider hard limits may be higher (currently 32 MB). Input and output language is English. No concurrency cap is imposed under this Agreement unless stated in the Order Form.

## 7. Support and Updates
7.1 Support. Support channels are email and GitHub Issues. Target initial response time is within two Netherlands business days.

7.2 Updates. Updates are provided when available. Licensor has no obligation to deliver features or maintain backward compatibility beyond reasonable efforts under semantic versioning for minor and patch releases.

7.3 SaaS/Uptime. Not applicable (self-hosted deployment).

## 8. Ownership, Outputs, Feedback
8.1 Ownership. Licensor retains all intellectual property rights in the Software. No implied licenses are granted.

8.2 Outputs. Customer owns outputs generated from Customer-supplied inputs. Licensor may use non-identifying feedback to improve the Software.

8.3 Feedback. If Customer provides feedback, Licensor may use it without restriction and without obligation to Customer.

## 9. Term and Termination
9.1 Term. The term is set in the Order Form (Subscription Term). Unless stated otherwise, terms renew automatically for successive one-year periods unless either party gives thirty (30) days' written notice before the end of the current term.

9.2 Termination for cause. Either party may terminate for material breach on thirty (30) days' written notice if the breach is not cured. Licensor may terminate immediately for Customer insolvency or assignment for the benefit of creditors.

9.3 Effect of termination. Upon termination, Customer must stop using the Software and delete or destroy all copies. Sections 3, 5, 8, 9.3, and 10 survive termination.

9.4 Fees. Fees paid are non-refundable except as expressly stated in the Order Form (for example, pro-rata refunds when early termination rights apply).

## 10. Warranty; Disclaimer; Limitation of Liability
10.1 Warranty. Licensor warrants that it has the right to grant the licenses described in this Agreement.

10.2 Disclaimer. The Software is provided "as is" and "as available" and Licensor disclaims all other warranties, express or implied, including merchantability, fitness for a particular purpose, and non-infringement. Licensor does not warrant that the Software will be error-free or that all defects will be corrected.

10.3 Limitation of liability. Except for Customer payment obligations or breaches of Section 3 (Restrictions), neither party will be liable for indirect, incidental, consequential, special, exemplary, or punitive damages. Licensor's total liability under this Agreement is limited to the amounts paid by Customer in the twelve (12) months preceding the claim.

## 11. General
11.1 Governing law. The Agreement is governed by the laws of the Netherlands, excluding its conflict-of-law rules. The United Nations Convention on Contracts for the International Sale of Goods does not apply.

11.2 Dispute resolution. Disputes will be submitted to the competent courts of Amsterdam, the Netherlands.

11.3 Assignment. Customer may not assign or transfer the Agreement without Licensor's prior written consent. Licensor may assign the Agreement to an affiliate or in connection with a merger or sale of substantially all assets.

11.4 Notices. Notices must be in writing and sent to the addresses stated in the Order Form (email permitted if confirmed as received).

11.5 Force majeure. Neither party is liable for failure or delay due to causes beyond their reasonable control.

11.6 Entire agreement. This Agreement and the Order Form constitute the entire agreement regarding Commercial Use and supersede prior discussions. Changes must be in writing signed by both parties.

11.7 Order Form precedence. If the Order Form conflicts with this Agreement, the Order Form controls for the conflicting item.

11.8 Severability. If a provision is held unenforceable, the remainder remains in effect.

11.9 No waiver. Failure to enforce a provision is not a waiver of future enforcement.

11.10 Counterparts. The Agreement may be signed in counterparts, including electronic copies.

---

# Commercial Order Form Template

**Customer Legal Name:** ________________________________

**Effective Date:** ____________________

**Primary Contact:**
- Name: ________________________________
- Email: ________________________________
- Phone: ________________________________

**Billing Contact (if different):**
- Name: ________________________________
- Email: ________________________________
- Phone: ________________________________

## 1. Subscription term
- Initial term: ________________________________
- Renewal: auto-renew yearly unless terminated with 30 days' notice before the renewal date (or as specified below).

## 2. Pricing model (select one)
- [ ] Subscription (fair use)
  - Plan name: ________________________________
  - Billing frequency: [ ] annual upfront   [ ] quarterly in advance
  - Fee (EUR): EUR __________ per billing period
  - Fair use threshold: __________ conversions per month
  - Overage (if threshold exceeded in two consecutive months): EUR ______ per conversion
  - Early termination right: Customer may terminate effective end of any calendar quarter with 30 days' notice; Licensor refunds prepaid fees pro-rata for the unused period.
  - Minimum term: renews annually until terminated per Agreement.

- [ ] Per-PDF billing
  - Unit price: EUR ______ per successful conversion
  - Monthly minimum (if any): EUR ______
  - Billing: monthly in arrears, net 30 days

*(Strike out or leave unchecked the model that does not apply.)*

## 3. Counting and reporting
- Counting unit: one successful conversion per unique PDF (SHA-256 hash) or DOI.
- Retries: up to two failures or timeouts per PDF are not counted.
- Usage report format (upon request or when variable fees apply):
  - CSV columns: `timestamp_iso8601, pdf_sha256, doi(optional), result(success|fail|timeout), duration_ms`
  - Only rows with `result = success` are billable.
- Report delivery: Customer provides the report within ten (10) business days after month-end when requested or when variable fees apply.

## 4. Third-party providers
- Current provider: OpenAI (subject to provider terms).
- Customer acknowledges responsibility to comply with applicable provider terms.

## 5. Support
- Support channels: email __________________ ; GitHub Issues __________________
- Target response time: within two Netherlands business days.

## 6. Signatures

Licensor: ____________________________________    Date: ____________

Customer: ____________________________________    Date: ____________

---

For noncommercial use or the 30-day trial, refer to the Prosperity Public License 3.0.0 (`LICENSE`). EOF

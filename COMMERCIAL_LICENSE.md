# Commercial Software License Agreement (Self-Hosted)

**This Commercial Software License Agreement (“Agreement”)** is between **Tolboom Medical** (“Licensor”) and the customer identified in the **Order Form** (“Customer”). This Agreement is effective on the Effective Date stated in the Order Form.

## 1. Scope and Relationship to PPL
**1.1 Software.** The “Software” means Licensor’s PDF-to-Report/Podcast converter using a large language model (LLM), any executables, installers, configuration files, and documentation delivered by Licensor for self-hosted use.
**1.2 Relationship to PPL 3.0.0.** Noncommercial use and a 30-day commercial trial are governed by the **Prosperity Public License 3.0.0 (PPL)** in the repository `LICENSE`. This Agreement governs **Commercial Use** beyond the PPL trial. If there is a conflict, this Agreement controls for Commercial Use.
**1.3 Commercial Use.** Any use by or for an organization or for direct or indirect commercial advantage, including internal business operations.

## 2. License Grant; Permitted Users
**2.1 Grant.** Subject to payment and compliance, Licensor grants Customer a **non-exclusive, non-transferable, non-sublicensable**, organization-wide license to install and use the Software **on Customer-controlled systems** for Commercial Use during the Subscription Term specified in the Order Form.
**2.2 Users.** Use is limited to Customer’s employees. **Affiliates and contractors are not permitted** under this license; each organization must obtain its own license.
**2.3 No Source Code.** Delivery is in executable/binary form (including Python packages or bundled runtimes). No source code is provided under this Agreement.

## 3. Redistribution and Restrictions
**3.1 Redistribution under PPL.** Customer may **externally redistribute unmodified copies** of the Software **only under the PPL 3.0.0** for noncommercial purposes, provided all required notices are preserved. Customer may not grant any commercial rights to third parties; **any third party requires its own commercial license** for Commercial Use.
**3.2 No service offering.** Customer may not host, rent, lease, lend, or offer the Software “as a service” to third parties.
**3.3 No competing training.** Customer may not use the Software or outputs to train or improve a model or service that competes with the Software.
**3.4 No reverse engineering.** Except to the limited extent allowed by mandatory law.
**3.5 Legal compliance.** Customer will comply with all applicable laws.

## 4. Third-Party Providers (Pass-Through)
**4.1 Providers.** The Software may call third-party LLM providers (currently OpenAI). Customer must comply with applicable **Provider Terms**, including content/safety, export, and use-case restrictions.
**4.2 Changes.** Licensor may switch or add Providers. Customer will not use the Software in a way that causes Licensor or any Provider to breach Provider Terms.
**4.3 Suspension.** Licensor may suspend use if Customer’s use violates Provider Terms or creates material risk.

## 5. Metrics, Fees, and Fair Use
**5.1 Pricing Model.** As specified in the Order Form: **Subscription with Fair Use** or **Per-PDF**.
**5.2 Counting Unit (Per-PDF).** A chargeable conversion is a **successful run** for a **unique input** identified by **(a) SHA-256 hash of the PDF file contents) or (b) DOI**, as reported by Customer; **duplicates do not count**.
**5.3 Retries/Timeouts.** Up to **two (2) retries** per PDF due to failure/time-out are **not billable**. Jobs exceeding **10 minutes** wall-clock time **auto-fail and are not billable**.
**5.4 Fair Use (Subscription).** The Order Form specifies a **Fair Use Threshold** (conversions per month). Persistent excess (two consecutive months) allows Licensor to **(i)** move Customer to a higher tier or **(ii)** invoice **overage** at the rate stated in the Order Form.
**5.5 No Telemetry.** The Software does **not** transmit usage data to Licensor. Customer must **maintain internal usage records** sufficient to substantiate reported counts.
**5.6 Reports.** Customer will provide a monthly **usage report/export** (CSV/JSON) on request and for any month with variable fees, in the format stated in the Order Form.

## 6. Delivery; System Limits
**6.1 Delivery.** Electronic delivery of installer or package; Customer is responsible for environment prerequisites.
**6.2 Limits.** **Max PDF size 10 MB**. **English-language input/output** only. **No concurrency cap** under this Agreement.

## 7. Support and Updates
**7.1 Support.** Email and GitHub Issues. Response target: **within two (2) NL business days**.
**7.2 Updates.** Provided **when available**; no obligation to deliver features or maintain backward compatibility beyond reasonable efforts under semantic versioning for minor/patch versions.
**7.3 SaaS/Uptime.** Not applicable (self-hosted).

## 8. Ownership; Outputs; Feedback
**8.1 Ownership.** Licensor retains all IP rights in the Software. No implied licenses.
**8.2 Outputs.** Customer owns outputs generated from Customer-supplied inputs. Licensor may use **non-identifying aggregate statistics** that Customer provides in reports to operate pricing and capacity planning.
**8.3 Feedback.** If Customer submits feedback, Licensor may use it without restriction.
*Note:* The Software itself **does not log or phone home**. Any usage statistics in 8.2 refer only to **Customer-reported** aggregates.

## 9. Fees; Taxes; Payment
**9.1 Fees.** As per the Order Form. All fees are **exclusive of taxes**.
**9.2 VAT/Taxes.** VAT and other applicable taxes will be added as required by Dutch/EU law. If reverse-charge applies, Customer will **self-account**; otherwise VAT is charged. Customer is responsible for all taxes other than Licensor’s income taxes.
**9.3 Invoicing and Payment.** Invoices net **30 days** from date of invoice, in **EUR**. Late amounts may accrue interest at the lesser of 1% per month or the maximum permitted by law. Purchase orders are not required unless specified in the Order Form.

## 10. Verification and Audit
**10.1 Self-reporting.** Customer will keep accurate internal records of conversions sufficient to verify fees.
**10.2 Audit.** No more than **once per 12 months**, on **30 days’ notice**, Licensor may audit during business hours. If under-reporting > **5%**, Customer pays shortfall, reasonable audit costs, and applicable interest.

## 11. Confidentiality
Neither party expects to exchange confidential information; if it happens, the receiving party will protect it using reasonable measures and use it only for this Agreement.

## 12. Warranties; Disclaimers
The Software is provided **“as is”**. Licensor disclaims all warranties to the fullest extent permitted by law.

## 13. Indemnity
**13.1 IP Indemnity by Licensor.** Licensor will defend Customer against third-party claims alleging that the unmodified Software directly infringes IP rights and pay resulting damages finally awarded, provided Customer promptly notifies Licensor and gives control of defense.
**13.2 Exclusions.** Claims arising from (i) combination with items not supplied by Licensor, (ii) Customer’s modifications, or (iii) use contrary to this Agreement or Provider Terms.
**13.3 Remedies.** Licensor may (i) modify the Software, (ii) replace it, or (iii) terminate the license and refund prepaid, unused fees.

## 14. Liability Cap
**14.1 Cap.** Licensor’s aggregate liability is limited to **fees paid by Customer in the 12 months** before the event.
**14.2 Exclusions.** Neither party is liable for indirect, incidental, special, consequential, or punitive damages.

## 15. Term; Termination
**15.1 Term.** As set in the Order Form; subscriptions **continue until terminated**.
**15.2 Termination for Cause.** Either party may terminate for material breach with **14 days** to cure after written notice. Licensor may terminate immediately for non-payment after notice.
**15.3 Effect.** On termination, **Commercial Use must cease**; Customer may keep outputs already generated. Sections intended to survive do so.

## 16. Export; Government Use
Customer will comply with applicable export laws (EU/US). Government use is subject to the same commercial terms.

## 17. Publicity; Assignment; Notices; Miscellaneous
**17.1 Publicity.** Neither party may use the other’s names or logos without prior written consent.
**17.2 Assignment.** Neither party may assign without consent, except by operation of law in merger/asset sale (not to a direct competitor).
**17.3 Notices.** To the contacts in the Order Form; email permitted.
**17.4 Entire Agreement.** Includes the Order Form and this Agreement; supersedes prior terms for Commercial Use. Amendments must be in writing.
**17.5 Severability; Waiver.** Standard.
**17.6 Language.** English governs. Any translation is for convenience.

## 18. Governing Law; Forum
**Dutch law** governs. The competent courts in **Groningen, Netherlands** have exclusive jurisdiction.

---

### Signatures
**Tolboom Medical** (Licensor)
Name: _________________________
Title: _________________________
Signature: _____________________  Date: __________

**Customer**
Legal Name: ____________________
Authorized Signer: _____________
Signature: _____________________  Date: __________


---

# Order Form (Commercial Use)

**Licensor:** Tolboom Medical
**Customer:** ______________________________
**Effective Date:** ____ / ____ / ______
**Subscription Term:** ☐ Annual (renews yearly; see Section 2A for quarterly termination) ☐ Other: __________
**Governing Documents:** This Order Form + Commercial Software License Agreement (Self-Hosted)

## 1) Deployment and Scope
- **Deployment:** Self-hosted (on Customer-controlled systems)
- **Permitted Users:** Customer’s employees only (no affiliates/contractors)
- **Territory:** Worldwide
- **Language:** English only
- **Max PDF Size:** 10 MB
- **Timeout per Conversion:** 10 minutes (then no-charge failure)
- **Concurrency:** Unlimited

## 2) Pricing Model (choose one)

**A. Subscription with Fair Use**
- **Plan Name:** __________________________
- **Billing:** ☐ Annual upfront ☐ Quarterly in advance
- **Fee (EUR):** € __________ per **year** (or € __________ per **quarter**)
- **Fair Use Threshold:** __________ conversions / month
- **Overage (if two consecutive months above threshold):** € ______ / conversion
- **Early Termination Right:** Customer may terminate effective **end of any calendar quarter** with **30 days’ notice**; Licensor refunds prepaid fees **pro-rata** for the remaining period.
- **Minimum Term:** Renews annually until terminated per Agreement

**B. Per-PDF**
- **Unit Price:** € ______ / successful conversion
- **Monthly Minimum (if any):** € ______
- **Billing:** Monthly in arrears, net 30 days

*(Strike out the model not used.)*

## 3) Counting and Reporting
- **Counting Unit:** One successful conversion per **unique input** as identified by **SHA-256 of the PDF** or **DOI** reported by Customer. Identical SHA-256 or DOI = **duplicate** → not counted.
- **Retries:** Up to **2** failures/time-outs per PDF are not counted.
- **Usage Report Format (when requested or for variable billing):**
  - **CSV columns:** `timestamp_iso8601, pdf_sha256, doi(optional), result(success|fail|timeout), duration_ms`
  - Only **success** rows are billable.
  - The Software performs **no telemetry**; Customer produces this report from internal logs/process accounting.
- **Report Delivery:** On request by Licensor and for any month with variable fees; within **10 business days** after month-end.

## 4) Third-Party Providers
- **Current Provider:** OpenAI (subject to Provider Terms).
- **Customer Acknowledgment:** Customer will ensure use complies with Provider Terms.

## 5) Support
- **Channels:** Email: __________________ ; GitHub Issues: __________________
- **Response Target:** within **2 NL business days**.

## 6) Invoicing and Taxes
- **Invoice Email:** __________________________
- **Currency:** EUR
- **Payment Terms:** Net **30 days**
- **VAT:** Charged as required under Dutch/EU law. If reverse-charge applies, Customer self-accounts.

## 7) Special Terms (if any)
- ____________________________________________________________________
- ____________________________________________________________________
- ____________________________________________________________________

### Acceptance
**Tolboom Medical** (Licensor) – Authorized Signer: __________________  Date: _________
**Customer** – Authorized Signer: ____________________________________  Date: _________

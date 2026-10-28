# Safety deliverables: default points

Date: 2026-10-28. Platform safety plan, autonomous wheel loader programme (project HWL).

**The question asked of each estimator.** For each of the 48 deliverables of the platform safety plan: how many points of an 8-point sprint does a normal functional safety engineer need to complete this deliverable, from draft to verified and reviewed, counting the FuSa engineer's own productive days only?

**The sprint rule (owner's decision, 2026-10-28).** A sprint spans 10 business days (weekends and holidays excluded); capacity is 8 points per sprint by company policy, so 1 point = one productive day. A deliverable may exceed 8 points and span sprints.

**Method.** Three independent estimators (A, B, C) each saw the whole plan (the 48 rows with phase, location, QMS references, author and reviewer roles) and the engineer's weekly status tracker for Phase 2 (Oct 12 to Oct 27, 2026) and the Sprint 2 commitments, and never saw each other's answers. A fourth decided per row from the three numbers and their reasons: the median is the default, moved off only where one estimator's reason was clearly better grounded in the status text or the QMS references, with the reason column saying so; rows of the same kind (the four STPA steps, the FuSa-authored concept documents, the records other roles own that the FuSa engineer only reviews) were checked against each other for a consistent scale. No row was moved off the median: the three sheets never spread by more than 2 points except on row 13, and the medians already sit in a consistent order within each kind. Every row where the three estimates spread by more than 3 points (max minus min) is flagged for the owner's eye.

**Totals.** A: 186 points. B: 165 points. C: 171 points. Consensus: 174 points, which is 21.75 sprints at 8 points per sprint (a little under 22 full sprints of the FuSa engineer's productive days, across the whole lifecycle).

Titles are reproduced from the plan; the two titles that contain line breaks are shown on one line in the table below and kept exactly, line breaks included, in consensus.json.

## Points per deliverable

| id | order | lifecycle phase | deliverable | A | B | C | points | flag | reason |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 1. Concept Development | Safety Plan | 5 | 5 | 4 | **5** |  | Median; A and B read the tracker the same way: structured in Sprint 1 but still to be dated against the programme schedule and baselined through U3 in Sprint 2 (HWL-2554), which is more than C's two remaining days cover. |
| 2 | 2 | 1. Concept Development | SCOPE Definition Report | 4 | 3 | 3 | **3** |  | Median; a bounded QF-12 report that reached draft inside Sprint 1 and needs one U3 review loop to release in DMS and Jama, and it sits below the Safety Plan among the three FuSa-authored Phase 1 documents. |
| 3 | 3 | 1. Concept Development | System Functions, Functional Architecture and its Interfaces | 2 | 2 | 2 | **2** |  | Unanimous; architect-owned under QP-06 and reviewed by the systems lead, the FuSa share is confirming with the systems team that the set is complete (an open ask in the tracker) and one review pass as STPA input. |
| 4 | 4 | 1. Concept Development | ConOps / Use Case specification | 2 | 1 | 2 | **2** |  | Median; architect-owned Jama content the tracker says is not yet seen, so locating it plus one hazard-oriented review pass is two days, level with row 3. |
| 5 | 5 | 1. Concept Development | TOD/PRD document | 1 | 1 | 1 | **1** |  | Unanimous; a PDP-16/17 document whose definition and owner are still being confirmed, where the FuSa engineer is neither author nor reviewer and reads it once for operational-domain inputs. |
| 6 | 6 | 1. Concept Development | Activity Flow | 3 | 3 | 3 | **3** |  | Unanimous; one DMS flow diagram drafted in Sprint 1 with review and baseline committed in Sprint 2 (HWL-2553). |
| 7 | 7 | 1. Concept Development | Preliminary Hazard List (STPA Step 1 outputs -losses, hazards, constraints) | 6 | 5 | 4 | **5** |  | Median; FuSa-authored QF-18 list drafted in Sprint 1 with the STPA practitioners, then peer review and approval as two Sprint 2 stories (HWL-2572/2573) with two tech-lead reviewers, which is more than C's four but A's six counts the review stories as if they were analysis. |
| 8 | 8 | 2. HARA / Risk Assessment | STPA step 2 | 6 | 4 | 4 | **4** |  | Median; B and C are better grounded in the tracker (the FSE drafted it in Sprint 1 and carries completion into Phase 3) while the architect and practitioners stay the nominal authors, so Step 2 sits just below Step 1 and well below Steps 3 and 4. |
| 9 | 9 | 2. HARA / Risk Assessment | HARA report with MPLr/PLr assignments | 10 | 8 | 8 | **8** |  | Median; B and C read the status text the same way, a Sprint 1 draft that still needs a full sprint of completion and U3 verification, and 8 keeps the HARA level with the TSC and below the FSC among the FuSa-authored analysis documents. |
| 10 | 10 | 3. Functional Safety Concept (FSC) | FTA/FMEA analysis for each SGs | 12 | 10 | 10 | **10** |  | Median; one FTA and FMEA per safety goal under QP-31 scales with the HARA's safety-goal count and spans sprints, level with the FSC it feeds. |
| 11 | 11 | 3. Functional Safety Concept (FSC) | STPA Step 3 results | 8 | 8 | 8 | **8** |  | Unanimous; UCA tables for every control action in the Step 2 control structure, a full sprint of analysis that Sprint 2 only starts (HWL-2574), sitting between Step 2 and Step 4. |
| 12 | 12 | 3. Functional Safety Concept (FSC) | System Architecture | 2 | 1 | 2 | **2** |  | Median; architect-owned and reviewed by the systems lead, the FuSa engineer reads it for allocation and independence, the same two days as rows 3 and 4. |
| 13 | 13 | 3. Functional Safety Concept (FSC) | Functional safety Concept | 12 | 10 | 8 | **10** | yes | Median, flagged for a 4-point spread; B's reading as the core Phase 3 document deriving FSRs from the HARA and UCAs with a full U3 cycle is the best grounded, and 10 keeps the FSC above the TSC and HARA (8) and level with the FTA/FMEA. |
| 14 | 14 | 4. System Design and Development | Allocation of FSR to System Requirements (to be Tagged as TSR) | 3 | 3 | 3 | **3** |  | Unanimous; the architect tags in Jama while the FuSa engineer verifies traceability of every FSR under U3 and closes findings, one step above a plain review. |
| 15 | 15 | 4. System Design and Development | TSC | 10 | 8 | 8 | **8** |  | Median; the platform_tsc template refining each FSR into technical safety requirements with a full U3 cycle fills one sprint, and the TSC sits below the FSC it derives from. |
| 16 | 16 | 4. System Design and Development | TSR (System Requirements) Review | 4 | 4 | 4 | **4** |  | Unanimous; a QP-31 review record over the whole tagged TSR set, structured review and comment closure rather than new analysis. |
| 17 | 17 | 4. System Design and Development | STPA Step 4 results | 10 | 10 | 10 | **10** |  | Unanimous; loss scenarios for every UCA is the broadest STPA step, only scoped and scheduled in Sprint 2 (HWL-2575), and it tops the four steps. |
| 18 | 18 | 4. System Design and Development | System architecture drawings with component description, States and Times | 2 | 2 | 2 | **2** |  | Unanimous; architect-owned drawings, the FuSa engineer verifies safe states and fault-reaction times against the TSC under U3. |
| 19 | 19 | 4. System Design and Development | Component safety specifications (HW and SW) | 3 | 3 | 3 | **3** |  | Unanimous; architect-owned HW and SW component specifications, the FuSa engineer verifies that each TSR is carried into a component specification under U3, one step above a drawing review. |
| 20 | 20 | 5. HW & SW Design and Development | Hardware Safety Requirements (HW-SR) | 3 | 2 | 3 | **3** |  | Median; a mechatronics-authored requirement set with both U3 verification and a QP-06 review on it, so the FuSa share is traceability verification plus comment closure, level with the SW-SR row. |
| 21 | 21 | 5. HW & SW Design and Development | Hardware Architecture Design, Category, MPL | 4 | 3 | 3 | **3** |  | Median; electronics-authored, the FuSa engineer checks the Category, MTTFd, DC and CCF claims per safety function against ISO 13849/25119, more than a read-through but not A's four. |
| 22 | 22 | 5. HW & SW Design and Development | HW-FMEA report | 3 | 3 | 3 | **3** |  | Unanimous; electronics-authored QP-32 FMEA spread across DMS, Jama and SharePoint, the FuSa engineer reviews failure modes and detection coverage per channel. |
| 23 | 23 | 5. HW & SW Design and Development | FMEDA report | 6 | 6 | 5 | **6** |  | Median; FuSa-authored from supplier data with PFH, DC and SFF per channel and U3 verification, and it sits above the PL/AgPL records it feeds. |
| 24 | 24 | 5. HW & SW Design and Development | Hardware Architecture Verification Report | 2 | 2 | 2 | **2** |  | Unanimous; a reliability-engineer report on which the FuSa engineer performs the U3 verification review. |
| 25 | 25 | 5. HW & SW Design and Development | SW-FMEA report | 3 | 2 | 3 | **3** |  | Median; an embedded-software QP-32 FMEA with U3 and QP-06 review, and the FuSa review of failure modes and mitigations matches the HW-FMEA row. |
| 26 | 26 | 5. HW & SW Design and Development | Software safety Requirements (SW-SR) | 3 | 2 | 3 | **3** |  | Median; a mechatronics-authored requirement set with U3 verification and QP-06 review, level with the HW-SR row. |
| 27 | 27 | 5. HW & SW Design and Development | Software Design Architecture | 2 | 2 | 2 | **2** |  | Unanimous; software-engineer-owned, the FuSa engineer reviews partitioning and freedom from interference of the safety-related components. |
| 28 | 28 | 5. HW & SW Design and Development | Software Architecture Verification Report | 2 | 1 | 2 | **2** |  | Median; a software-engineer-owned verification report with both U3 and QP-06 review on it, two days like the other verification reports. |
| 29 | 29 | 5. HW & SW Design and Development | Software component Design and coding verification report | 2 | 2 | 2 | **2** |  | Unanimous; software-engineer-owned, the FuSa engineer reviews coding-standard and design verification evidence for the safety-related components. |
| 30 | 30 | 6. Integration and Testing | Hardware component test plan, specification and report | 2 | 2 | 2 | **2** |  | Unanimous; V&V-authored under the QM validation plan, the FuSa engineer reviews coverage of the HW-SRs and the results. |
| 31 | 31 | 6. Integration and Testing | Software component test plan, specification and report | 2 | 2 | 2 | **2** |  | Unanimous; V&V-authored under the QM validation plan, the FuSa engineer reviews coverage of the SW-SRs and the results. |
| 32 | 32 | 6. Integration and Testing | Hardware System Integration Test Plan & Specification, Results | 2 | 2 | 2 | **2** |  | Unanimous; V&V-authored, the FuSa engineer reviews that the integration tests exercise the TSRs and safety mechanisms. |
| 33 | 33 | 6. Integration and Testing | Software integration test plan, specification and report. | 2 | 2 | 2 | **2** |  | Unanimous; V&V-authored, the FuSa engineer reviews integration coverage of the SW-SRs and the results. |
| 34 | 34 | 6. Integration and Testing | Software test plan, specification and report | 2 | 2 | 2 | **2** |  | Unanimous; V&V-authored, the FuSa engineer reviews requirement-based test coverage and the results. |
| 35 | 35 | 6. Integration and Testing | System and Vehicle test plan and reports | 3 | 3 | 3 | **3** |  | Unanimous; several vehicle-level plans and reports to review for TSR coverage and fault-injection cases, one step above the component and integration rows. |
| 36 | 36 | 7. Safety Validation | System validation & Verification test plan, specification and report | 4 | 3 | 4 | **4** |  | Median; the deepest review of the test set, confirming every safety goal and FSR has validation evidence against the HARA, so it tops the V&V rows. |
| 37 | 37 | 7. Safety Validation | Field test evidence | 2 | 2 | 2 | **2** |  | Unanimous; V&V-collected evidence the FuSa engineer reviews as validation evidence for the safety goals. |
| 38 | 38 | 7. Safety Validation | PL/AgPL achievement records | 5 | 5 | 5 | **5** |  | Unanimous; FuSa-authored per-safety-function PL/AgPL claims from Category, MTTFd, DC, CCF and the FMEDA inputs, with U3 verification, just below the FMEDA. |
| 39 | 39 | 7. Safety Validation | TOD operational validation evidence | 2 | 2 | 2 | **2** |  | Unanimous; V&V-collected evidence the FuSa engineer reviews against the TOD operational assumptions of the HARA. |
| 40 | 40 | 7. Safety Validation | Stop system validation records | 2 | 3 | 3 | **3** |  | Median; B and C are right that the layered stop system (E-stop, all-stop, geofence, proximity monitor, heartbeat, as presented in onboarding) carries the highest PLr and each layer's evidence is reviewed, so it sits above the generic evidence rows. |
| 41 | 41 | 8. Functional Safety Assessment | • FSA plan  • FSA report  • Safety Case  • Certification evidence package (optional) | 14 | 12 | 14 | **14** |  | Median; four work products on three QMS references, with the Safety Case arguing from every preceding deliverable's evidence, the largest authoring effort in the plan at close to two sprints. |
| 42 | 42 | 9. Production and Operation | Product Safety Release Letter | 1 | 1 | 2 | **1** |  | Median; a QF-19 standard sign-off form completed in a day once the FSA closes, with the tech-lead sign-off inside it. |
| 43 | 43 | 9. Production and Operation | Change management records | 1 | 1 | 1 | **1** |  | Unanimous; robot-team QP-12 records reviewed by the respective area lead, the FuSa engineer only screens each change for safety impact. |
| 44 | 44 | 9. Production and Operation | Risk Assessment Records | 1 | 1 | 1 | **1** |  | Unanimous; robot-team records reviewed by PAT, the FuSa contribution is a consistency read against the HARA. |
| 45 | 45 | 9. Production and Operation | Periodic safety review reports | 2 | 2 | 2 | **2** |  | Unanimous; a short recurring report co-authored with the product manager, robot chief and tech lead, where the FuSa engineer prepares the safety input and the record. |
| 46 | 46 | 9. Production and Operation | Production control procedures and plan | 1 | 1 | 1 | **1** |  | Unanimous; a production-team plan reviewed by occupational safety, the FuSa engineer only confirms the safety-relevant production controls are listed. |
| 47 | 47 | 9. Production and Operation | User and Repair Instruction Manual  • Operator training records  • Field safety monitoring records | 2 | 2 | 2 | **2** |  | Unanimous; three work products owned by other teams with no FuSa role on the row, two days to check that residual risks and safety instructions from the HARA carry through, one above the single-record rows 43, 44 and 46. |
| 48 | 48 | 10. Decommissioning | •ASI Decommissioning procedure | 1 | 1 | 2 | **1** |  | Median; a short procedure with no named author reviewed by three tech leads, one day for the FuSa review of safe-state and energy-isolation steps, level with the other rows where FuSa does not author. |
| | | | **Total** | **186** | **165** | **171** | **174** | | 21.75 sprints at 8 points |

## Rows to look at

Rows where the three estimates spread by more than 3 points: 1.

### Row 13: Functional safety Concept (A 12, B 10, C 8; decided 10)

| estimator | points | reason |
|---|---|---|
| A | 12 | Platform FSC template deriving functional safety requirements, safety mechanisms, degraded states and warning concepts from every safety goal, then U3 verification. |
| B | 10 | The platform FSC on the platform_fsc template: deriving FSRs from the HARA and UCAs, allocating them to the architecture and verifying them through U3; the core Phase 3 document. |
| C | 8 | FuSa-authored platform FSC deriving functional safety requirements and safe states from the HARA for all safety goals, U3 verified: a sprint of authoring and review incorporation. |

Decision: Median, flagged for a 4-point spread; B's reading as the core Phase 3 document deriving FSRs from the HARA and UCAs with a full U3 cycle is the best grounded, and 10 keeps the FSC above the TSC and HARA (8) and level with the FTA/FMEA.

## How to use

The consensus `points` column seeds `default_points` on the Safety Plan row in asi_kletz, one integer per deliverable, keyed by the deliverable's id and order from the plan. A deliverable's actual points can be set on the row when the work is planned; the default is the starting value when none has been set.

Re-running the estimate (same question, same plan, same tracker, three fresh independent estimators and a fourth to decide) produces a new consensus; compare it as a diff against this file, row by row, and treat any row that moves by more than 2 points as a change to explain rather than a change to accept silently. Keep this file beside the plan as the record of where the first defaults came from.

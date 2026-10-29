Related Links:

[Top-level STPA](https://example.invalid/wiki/spaces/STPA/pages/800000001/Top-level+STPA) (System STPA)


## Losses and Hazards

**LOSSES**:

L1 - A person is injured by the gate

L2 - The conveyor line stops for longer than a shift

**HAZARD FOCUS**:

H1 - The gate closes while a person is in the opening *\[L1\]*

H2 - The gate stays open while the belt runs *\[L1, L2\]*

H2.1 - Nearby workers are unaware that the belt is about to run

H3 - The gate controller loses the supervisor's hold request *\[L2\]*

~~H4 - An old hazard, retired~~

---

## Control Structure

The gate controller closes the gate before the belt runs; the supervisor can hold the gate open.

---

## Context Table

| **Controller** | **Control Action** | **Not Providing**Missing | **Providing**When not expected | **Incorrect Timing / Incorrect Order**Too Early/Too Late | **Stopped Too Soon / Applied Too Long**Truncated Stuck |
| --- | --- | --- | --- | --- | --- |
| Gate Controller | Close Gate | **UCA1 **When the belt is about to run. *\[H2, H2.1\]***UCA2 **When the supervisor's hold has expired. *\[H2, H9\]***~~UCA3 ~~**~~When the line restarts after a fault.~~ *~~\[H2\] ~~(duplicate of **UCA6**)* | **UCA4 **While a person is in the opening. *\[H1\]* | **UCA5 **Too late, after the belt has started. *\[H2\]* |  |
| Supervisor | Hold Request | **UCA6 **When maintenance is in the opening. *\[H1\]* |  | **UCA7 **Too late, after the gate has started to close. *\[H1\]* | **UCA8 **Held after maintenance has left. *\[H2\]* |
| Belt Drive | Run Belt | [Belt Drive STPA](https://example.invalid/wiki/spaces/STPA/pages/800000002) |  |  |  |

---

## Loss Scenarios

|  | **UCA** | **Type** | **Causal Factors** | **Constraints** |
| --- | --- | --- | --- | --- |
| 1 | **UCA1 **The gate controller does not close the gate when the belt is about to run.*True Statement:**The belt is about to run.* | **Type 1: **Inadequate control algorithm / hardware**Type 1: **Inadequate process model*Belief:**The gate is already closed.***Type 2: **Inadequate feedback and information | The gate position sensor is stuck. The run request is not received. | **CSTR1 **The gate controller must confirm the gate position before every run.**CSTR2 **A stuck position sensor must be treated as a fault. |
| 2 | **CA1 **The gate controller does close the gate when the belt is about to run. | **Type 3: **Control Path**Type 4: **Controlled Process | The close command is sent but the gate drive does not move. | **CSTR1 **and **CSTR2 ****CSTR3 **The gate drive must report a failed close within one second. |
| 3 | **UCA2 **The gate controller does not close the gate when the hold has expired. | **Type 1: **Inadequate control algorithm / hardware**Type 2: **Inadequate feedback and information | The hold timer is not synchronised. | **CSTR4 **An expired hold must close the gate without a new request. |
| 4 | **CA2** | **Type 3: **Control Path**Type 4: **Controlled Process | (covered on UCA1) | **CSTR1 **and **CSTR3** |
| 5 | **~~UCA3 ~~**~~The gate controller does not close the gate when the line restarts after a fault.~~ | **~~Type 1: ~~**~~Inadequate control algorithm / hardware~~ | ~~(duplicate of UCA6)~~ | ~~**CSTR1**~~ |
| 6 | **UCA5 **The gate controller closes the gate too late, after the belt has started. | **Type 1: **Inadequate control algorithm / hardware**Type 2: **Inadequate feedback and information | Processing delays. | **CSTR5 **The close must complete before the belt reaches speed. |
| 7 | **CA5 **The gate controller closes the gate on time. | **Type 3: **Control Path**Type 4: **Controlled Process | The gate drive is slow because its supply is low. | **CSTR3 **and **CSTR5** |
| 8 | **UCA6 **The supervisor does not request a hold when maintenance is in the opening. *\[H1\]* | **Type 1: **Inadequate process model*Belief:**Maintenance has left.* | The maintenance sign-out is not visible from the desk. | **CSTR3 **and **CSTR6 **Maintenance presence must be shown at the supervisor's desk. |
| 9 | UCA7 The supervisor requests a hold too late *\[H1\]* | **Type 1: **Inadequate control algorithm / hardware | Feedback delays. | **CSTR5 **and **CSTR6** |
| 10 |  | **Type 3: **Control Path**Type 4: **Controlled Process |  |  |

Related Links:

[Top-level STPA](https://example.invalid/wiki/spaces/STPA/pages/800000001/Top-level+STPA) (System STPA)


## Losses and Hazards

**HAZARD FOCUS**:

H1 - The gate closes while a person is in the opening

H2 - The gate stays open while the belt runs

H2.1 - Nearby workers are unaware that the belt is about to run

H2.2 - Other lines are unaware of the gate's state

---

## Control Structure

The gate controller closes the gate before the belt runs; the supervisor can hold the gate open.

---

## Context Table

| **Controller** | **Control Action** | **Not Providing**Missing | **Providing**When not expected | **Incorrect Timing / Incorrect Order**Too Early/Too Late | **Stopped Too Soon / Applied Too Long**Truncated Stuck |
| --- | --- | --- | --- | --- | --- |
| Gate Controller | Close Gate | **UCA1 **When the belt is about to run. *\[H2\]***UCA2 **When the hold has expired. *\[H2, H2.1\]***~~UCA3 ~~**~~When the line restarts after a fault.~~ *~~\[H2\] ~~(duplicate of **UCA9**)* | **UCA4 **While a person is in the opening. *\[H1\]* | **UCA5 **Too late, after the belt has started. *\[H2\]* |  |
| Hold Gate | (duplicate of **UCA6** here) | **UCA7 **When the gate is already closing. *\[H1\]* | **UCA8 **Too late, after the belt has started. *\[H2\]* |  |  |
| Signal Lamp | **UCA10 **When the belt is about to run. *\[H2.1, H9\]***UCA11** When a line restarts {after a fault}. *\[H2.2\]*UCA12 When the lamp is masked by dust. *\[H2.1\]* | **UCA13** While maintenance is in the opening. *\[H1\]* |  | **UCA14 **Left on after the belt has stopped. |  |
| Supervisor | Hold Request | **UCA6 **When maintenance is in the opening. *\[H1\]* | **UCA9 **Held after maintenance has left. *\[H2\]* |  |  |
| Belt Drive | Run Belt | (duplicate of the signal lamp row) |  |  |  |
| Belt Drive | Lamp Test | **UCA6 **A code read twice by mistake. *\[H1\]* |  |  |  |

---

## Loss Scenarios

|  | **UCA** | **Type** | **Causal Factors** | **Constraints** |
| --- | --- | --- | --- | --- |
| 1 | **UCA1 **The gate controller does not close the gate when the belt is about to run. | **Type 1: **Inadequate control algorithm / hardware**Type 1: **Inadequate process model*Belief:**The gate is already closed.* | The gate position sensor is stuck. | **CSTR1 **The gate controller must confirm the gate position before every run.**CSTR2 **A stuck position sensor must be treated as a fault. |
| 2 | **CA1 **The gate controller does close the gate when the belt is about to run. | **Type 3: **Control Path**Type 4: **Controlled Process | The close command is sent but the gate drive does not move. (same as UCA5 CF) | **CSTR\[1,2\]****CSTR3 **The gate drive must report a failed close within one second. |
| 3 | **UCA6 **The supervisor does not request a hold when maintenance is in the opening. | **Type 1: **Inadequate process model*Belief:**Maintenance has left.* | The maintenance sign-out is not visible from the desk. | duplicate **CSTR3** |
| 4 | **UCA7 **The gate controller does not close the gate when it is already closing. | **Type 2: **Inadequate feedback and information | The closing state is not reported. | **CSTR4 **The closing state must be reported every cycle. **see also CSTR2****duplicate CSTR\[1, 3\]** |
| 5 | **UCA9 **The supervisor holds the gate after maintenance has left. | **Type 1: **Inadequate control algorithm / hardware | Feedback delays. | **CSTR\[5 **A hold must expire with the shift. |
| 6 | UCA12 The signal lamp is masked by dust *\[H2.1\]* | **Type 4: **Controlled Process | Dust on the lens. | **duplicate CSTR5 and CSTR6** |

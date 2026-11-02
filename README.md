# Ignition Envelope Detection System

## Overview

This project implements reusable operational-envelope anomaly detection for servo tags in Ignition. The implementation consists of:

1. A reusable User-Defined Type (UDT)
2. A Gateway Timer Script
3. A Project Library evaluator
4. Two separate alarm outputs
5. A dedicated Alarm Journal
6. Current-day, completed-day, and weekly reporting functions

The design intentionally separates immediate notifications from historical reporting:

- `Hour_Alarm` represents the rolling 60-minute anomaly condition and can use an Alarm Notification Pipeline.
- `Hourly_Alert_Pulse` produces one short alarm activation for every qualifying completed clock hour. It has no notification pipeline and exists only for journaling and reports.

## Detection Flow

```text
Servo_Actual_Value
        |
        v
Compare against SERVO_MIN and SERVO_MAX
with Tolerance_Percent
        |
        v
Rolling sample window
        |
        v
Rolling_Alarm
        |
        +------------------------------+
        |                              |
        v                              v
Rolling 60-minute history       Fixed clock-hour counter
        |                              |
        v                              v
Hour_Alarm                    Hourly_Alert_Pulse
        |                              |
        v                              v
Notification Pipeline          Envelope_Alerts Journal
                                       |
                                       v
                         Current-day / Daily / Weekly reports
```

## Window Logic

### Stage 1: Sample-level rolling window

The evaluator samples the servo at the Gateway Timer interval and records whether each evaluation is outside the effective operational envelope.

```text
window size = Window_Seconds / Sample_Interval_Seconds
```

The effective limits are:

```text
tolerance = (SERVO_MAX - SERVO_MIN) * Tolerance_Percent
effective minimum = SERVO_MIN - tolerance
effective maximum = SERVO_MAX + tolerance
```

`Rolling_Alarm` is true when the completed sample window contains at least `Min_Outside_Samples` outside evaluations.

### Stage 2: Rolling 60-minute notification condition

One Boolean result is retained for each completed minute. The latest 60 completed minute results are stored in `Hour_History`.

`Hour_Alarm` becomes true when the rolling 60-minute history contains at least `Min_Alert_Minutes` abnormal minutes. The alarm on `Hour_Alarm` may use an Active Pipeline for immediate notification.

### Stage 3: Fixed clock-hour reporting event

`Current_Hour_Outside_Count` counts abnormal completed minutes within the current fixed clock hour. `Last_Hour_Key` identifies the hour currently being accumulated.

At each clock-hour boundary, the evaluator compares the completed hour count with `Min_Alert_Minutes`. If the completed hour qualifies, `Hourly_Alert_Pulse` becomes true for one Gateway Timer execution and then returns to false.

This creates one distinct Alarm Journal activation per qualifying clock hour, including consecutive anomaly hours, without sending a notification every hour.

## UDT Tag Specifications

| Name | Tag Type | Data Type | Default | Purpose |
|---|---|---:|---:|---|
| `Servo_Actual_Value` | Expression or Reference | Numeric | N/A | Monitored servo value. Each UDT instance points this member to the appropriate source tag. |
| `SERVO_MIN` | Memory | Numeric | `-1` | Lower operational-envelope limit. |
| `SERVO_MAX` | Memory | Numeric | `1` | Upper operational-envelope limit. |
| `Tolerance_Percent` | Memory | Float | `0` | Additional tolerance applied outside the configured envelope. Use `0.01` for 1%. |
| `Window_Seconds` | Memory | Integer | `60` | Duration of the sample-level rolling window. |
| `Sample_Interval_Seconds` | Memory | Float | `1` | Evaluator interval in seconds. This must match the Gateway Timer delay. |
| `Min_Outside_Samples` | Memory | Integer | Site-specific | Minimum outside samples required to activate `Rolling_Alarm`. |
| `Outside_History` | Memory | String | `""` | Comma-separated `0`/`1` sample results for the short rolling window. |
| `Outside_Count` | Memory | Integer | `0` | Number of outside evaluations in `Outside_History`. |
| `Rolling_Alarm` | Memory | Boolean | `False` | Intermediate sample-window anomaly result. |
| `Last_Minute_Key` | Memory | Long | `0` | Identifies the clock minute currently being evaluated. |
| `Last_Minute_Result` | Memory | Boolean | `False` | Retains whether the current minute has experienced `Rolling_Alarm`. |
| `Hour_History` | Memory | String | `""` | Latest 60 completed minute results used by the rolling hourly condition. |
| `Hour_Outside_Count` | Memory | Integer | `0` | Number of abnormal minutes in the rolling 60-minute history. |
| `Min_Alert_Minutes` | Memory | Integer | `1` | Minimum abnormal minutes required by both hourly evaluations. |
| `Hour_Alarm` | Memory | Boolean | `False` | Rolling 60-minute condition used for immediate notification. |
| `Current_Hour_Outside_Count` | Memory | Integer | `0` | Number of abnormal completed minutes in the current fixed clock hour. |
| `Last_Hour_Key` | Memory | Long | `0` | Identifies the fixed clock hour currently being accumulated. |
| `Hourly_Alert_Pulse` | Memory | Boolean | `False` | One-cycle pulse for each qualifying completed clock hour; journal/reporting only. |
| `Detector_Status` | Memory | String | `"Waiting"` | Human-readable evaluator status and diagnostics. |

The state/output members must be writable Memory Tags. The evaluator writes to histories, counts, alarms, keys, pulse, and status tags.

## Project Library Structure

The current Project Library structure is:

```text
Scripting
└── Project Library
    └── envelopeDetector
        └── evaluate
            └── def evaluate(basePath)
```

Because `envelopeDetector` is a package and `evaluate` is a script containing a function also named `evaluate`, the function call is:

```python
envelopeDetector.evaluate.evaluate(detectorPath)
```

If the resources are later simplified to a single script named `envelopeDetector`, the call becomes:

```python
envelopeDetector.evaluate(detectorPath)
```

Keep the complete evaluator in the `evaluate` Project Library script. Use four spaces for indentation and paste the code into Ignition as plain text to avoid Jython `expecting DEDENT` compilation errors.

## Gateway Timer Script

Recommended settings:

| Setting | Value |
|---|---|
| Delay | `1000 ms` |
| Enabled | `True` |
| Delay Type | `Fixed Delay` |
| Threading | `Dedicated` |

`Sample_Interval_Seconds` must be `1` when the Timer delay is `1000 ms`.

Example Timer Script:

```python
logger = system.util.getLogger("EnvelopeDetectorTimer")

detectors = [
    "[default]Anomaly_Detection/Line_4_Palletizer/M_10_Hoist",
    "[default]Anomaly_Detection/Line_4_Palletizer/M_11_Apron",
    "[default]Anomaly_Detection/Line_4_Palletizer/M_12_End_Compression"
]

for detectorPath in detectors:
    try:
        result = envelopeDetector.evaluate.evaluate(detectorPath)

        if not result:
            logger.warn(
                "Detector returned False | Path=%s"
                % detectorPath
            )

    except Exception as error:
        logger.error(
            "Unhandled detector error | Path=%s | Error=%s"
            % (
                detectorPath,
                str(error)
            )
        )
```

## Alarm Configuration

### `Hour_Alarm`: notification alarm

Keep the existing alarm on `Hour_Alarm` for immediate notification.

| Setting | Value |
|---|---|
| Enabled | `True` |
| Mode | `Equal` |
| Setpoint | `1` |
| Active Delay | `0` |
| Clear Delay | `0` |
| Active Pipeline | Project-specific notification pipeline |

A continuous anomaly episode generates one activation when `Hour_Alarm` transitions from false to true. The alarm does not repeatedly notify while `Hour_Alarm` remains true.

### `Hourly_Alert_Pulse`: journal-only alarm

Add a separate alarm to `Hourly_Alert_Pulse`.

| Setting | Value |
|---|---|
| Name | `Hourly_Envelope_Event` |
| Enabled | `True` |
| Priority | `Diagnostic` during testing |
| Mode | `Equal` |
| Setpoint | `1` |
| Active Delay | `0` |
| Clear Delay | `0` |
| Active Pipeline | Blank |
| Clear Pipeline | Blank |
| Ack Pipeline | Blank |

The pulse alarm must not use the notification pipeline. Its purpose is to create one Alarm Journal event for each qualifying completed clock hour.

## Alarm Journal

The dedicated Alarm Journal is named:

```text
Envelope_Alerts
```

The exact Ignition source format resembles:

```text
prov:default:/tag:Anomaly_Detection/Line_4_Palletizer/M_12_End_Compression/Hour_Alarm:/alm:Env_Excursion
```

Journal filtering should be tested against newly generated alarm events. If a configured journal filter prevents events from appearing, leave the journal filter blank and filter the results in `envelopeReports`. This is safer than silently dropping anomaly history.

To inspect the journal from the Script Console:

```python
events = system.alarm.queryJournal(
    startDate=system.date.addHours(
        system.date.now(),
        -24
    ),
    endDate=system.date.now(),
    journalName="Envelope_Alerts",
    includeSystem=False
)

print "Events found:", len(events)

for event in events:
    print "Source:", event.getSource()
    print "Display Path:", event.getDisplayPath()
    print "Label:", event.getLabel()
    print "State:", event.getState()
    print "-----"
```

## Reporting

The `envelopeReports` Project Library script provides:

```python
envelopeReports.getCurrentDayReport()
envelopeReports.getDailyReport()
envelopeReports.getWeeklyReport()
```

### Current-day report

Compares:

```text
Today from midnight through the current time
versus
Yesterday from midnight through the same elapsed time
```

Example:

```python
report = envelopeReports.getCurrentDayReport()

print report["subject"]
print
print report["text"]
```

### Completed-day report

Compares yesterday against the day before yesterday.

```python
report = envelopeReports.getDailyReport()
print report["text"]
```

### Weekly report

Compares the latest completed Monday-Sunday week against the completed week before it and includes a daily breakdown.

```python
report = envelopeReports.getWeeklyReport()
print report["text"]
```

### Reporting configuration

Use:

```python
JOURNAL_NAME = "Envelope_Alerts"
FINAL_ALARM_TAG_NAME = "Hourly_Alert_Pulse"
```

The reports count journaled active events produced by `Hourly_Alert_Pulse`, not the persistent `Hour_Alarm` condition.

### Equipment identification

Alarm Display Paths may contain only the generic alarm label, such as `Hourly Envelope Event`. Equipment grouping must therefore parse the UDT instance from the canonical alarm source.

Expected source:

```text
prov:default:/tag:Anomaly_Detection/Line_4_Palletizer/M_12_End_Compression/Hourly_Alert_Pulse:/alm:Hourly_Envelope_Event
```

The equipment helper should return the member immediately above `Hourly_Alert_Pulse`, such as:

```text
M_12_End_Compression
```

Use this helper in `envelopeReports`:

```python
def _equipment_name(event):
    try:
        if event.contains("Equipment"):
            equipment = str(event.get("Equipment"))

            if equipment:
                return equipment
    except:
        pass

    source = str(_event_source(event) or "")
    prefix = "prov:default:/tag:"

    if source.startswith(prefix):
        source = source[len(prefix):]

    if ":/alm:" in source:
        source = source.split(":/alm:", 1)[0]

    sourceParts = [
        part
        for part in source.split("/")
        if part
    ]

    if len(sourceParts) >= 2:
        return sourceParts[-2]

    return "Unknown Equipment"
```

Preserving underscores is recommended because the report output then matches the exact Ignition UDT instance name.

## Adding Another Servo

1. Create another detector UDT instance.
2. Configure `Servo_Actual_Value`, `SERVO_MIN`, and `SERVO_MAX`.
3. Set `Tolerance_Percent`, `Window_Seconds`, `Sample_Interval_Seconds`, `Min_Outside_Samples`, and `Min_Alert_Minutes`.
4. Add the instance path to the Gateway Timer Script's `detectors` list.
5. Confirm all input/reference tags have Good quality.
6. Confirm `Detector_Status`, `Outside_Count`, `Rolling_Alarm`, `Hour_Outside_Count`, and `Hour_Alarm` update.
7. Confirm `Last_Hour_Key` initializes and `Current_Hour_Outside_Count` increments once per abnormal completed minute.
8. Confirm a qualifying completed hour causes `Hourly_Alert_Pulse` to transition false → true → false.
9. Confirm `Hourly_Envelope_Event` appears in `Envelope_Alerts`.
10. Confirm reports group the event under the exact servo UDT instance.

## Troubleshooting

### Everything except `Servo_Actual_Value` appears paused

`Servo_Actual_Value` is an Expression or Reference Tag and can continue updating independently even when the Gateway Timer or Project Library evaluator fails.

Check Gateway logs for:

```text
EnvelopeDetector
EnvelopeDetectorTimer
```

Common causes:

- Gateway Timer is disabled.
- Project Library or Timer changes were not saved.
- The Timer uses the wrong Project Library call path.
- A Project Library syntax/indentation error prevents compilation.
- A required UDT member is missing or incorrectly named.

### `mismatched input ... expecting DEDENT`

The Project Library script contains inconsistent indentation or pasted hidden whitespace. Replace the script with a clean plain-text version using four spaces per indent level.

### `ProjectScriptModule object is not callable`

The call path does not match the package/script/function hierarchy. For the current nested structure, call:

```python
envelopeDetector.evaluate.evaluate(detectorPath)
```

### Detector reports bad quality

Check:

```text
Servo_Actual_Value
SERVO_MIN
SERVO_MAX
```

Do not bypass the quality check. Invalid source or envelope data can create false anomaly results.

For a documented temporary issue, the repetitive `logger.warn(...)` call inside the bad-quality branch may be commented out while retaining the fail-safe output reset and `return False`.

### Journal records no events

1. Temporarily remove the journal filter.
2. Generate a new false → true → false test event.
3. Query `Envelope_Alerts` from the Script Console.
4. Inspect the actual `Source`, `Display Path`, and `Label`.
5. Reapply a filter only after confirming its exact match behavior.

### Reports show `Hourly Envelope Event` as equipment

Replace the equipment helper with the canonical-source parser shown above. The generic Display Path or label does not identify the servo instance.

### Email notification fails

If the alarm and pipeline activate but email does not arrive, inspect Gateway logs for SMTP errors. A connection timeout to the configured SMTP host and port is separate from the detector, journal, and reporting logic.

`Hourly_Alert_Pulse` intentionally has no notification pipeline. Scheduled current-day, daily, or weekly report emails should use the reporting email mechanism only after SMTP connectivity is working.

## Repository

Project repository: [AJG-ACE/Ignition-Envelope-Detector](https://github.com/AJG-ACE/Ignition-Envelope-Detector)

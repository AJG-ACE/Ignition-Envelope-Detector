# Ignition Envelope Detection System

## Overview

The envelope detection system in Ignition consists of three parts:

1. A User-Defined Type (UDT)
2. A Gateway Timer Script
3. A Project Library Script

Together, these components detect sustained operation of a servo outside an operational envelope. The configurable parameters can be adjusted for the requirements of each use case.

## How It Works

The detector uses two rolling windows:

1. A sample-level window evaluates servo values against minimum and maximum envelope limits.
2. A minute-level window evaluates how many minutes within the hour contained an anomaly.

The final alarm is raised through `Hour_Alarm` when the configured number of anomalous minutes is reached.

## UDT

The UDT contains the parameters, alarms, history, state, and output tags required by the detector.

### UDT Tag Specifications

| Name | Tag Type | Data Type | Default Value | Purpose |
|---|---|---:|---:|---|
| `Detector_Status` | Memory | String | `"Waiting"` | Displays the current status of the envelope detection system. |
| `Hour_Alarm` | Memory | Boolean | `False` | Final alarm output for the envelope detector. |
| `Hour_History` | Memory | String | `""` | Stores the anomaly status of completed minute windows used by the hourly evaluation. |
| `Hour_Outside_Count` | Memory | Integer | `0` | Number of anomalous minutes in the current hourly history. |
| `Last_Minute_Key` | Memory | Long | `0` | Identifies the clock minute currently being processed. |
| `Last_Minute_Result` | Memory | Boolean | `False` | Stores whether the currently tracked minute has produced an anomaly. |
| `Min_Alert_Minutes` | Memory | Integer | `1` | **Parameter:** Number of anomalous minutes within an hour required to trigger `Hour_Alarm`. |
| `Outside_Count` | Memory | Integer | `0` | Number of samples in the current sample window that are outside the envelope. |
| `Outside_History` | Memory | String | `""` | Stores the anomaly status of samples in the current rolling sample window. |
| `Rolling_Alarm` | Memory | Boolean | `False` | Intermediate anomaly result for the current minute-level evaluation. |
| `Sample_Interval_Seconds` | Memory | Float | `1` | **Parameter:** Sample duration in seconds. This should match the Gateway Timer delay and is used to calculate the number of samples in the first window. |
| `Servo_Actual_Value` | Expression | Integer | N/A | **Parameter:** Reference or expression path to the monitored servo value. |
| `SERVO_MAX` | Memory | Integer | `1` | **Parameter:** Maximum operational-envelope value. |
| `SERVO_MIN` | Memory | Integer | `-1` | **Parameter:** Minimum operational-envelope value. |
| `Tolerance_Percent` | Memory | Float | `0` | **Parameter:** Additional tolerance applied outside the operational envelope. |
| `Window_Seconds` | Memory | Integer | `60` | **Parameter:** Length of the first rolling window. Together with `Sample_Interval_Seconds`, this determines the number of samples in the window. |

## Gateway Timer Script

Create a Gateway Timer Script with the following settings:

| Setting | Value |
|---|---|
| Delay | `1000 ms` |
| Enabled | `True` |
| Delay Type | `Fixed Delay` |
| Threading | `Dedicated` |

The Timer Script should call the reusable Project Library evaluator for each detector instance.

## Project Library Script

In the Project Library, create the following structure:

```text
Scripting
└── Project Library
    └── envelopeDetector
        └── evaluate
```

The `evaluate` script contains the dual-window evaluation function that determines sample-level and hourly anomalies.

## Alarm Configuration

Attach the notification-producing Ignition alarm to `Hour_Alarm`.

Recommended alarm settings:

| Setting | Value |
|---|---|
| Enabled | `True` |
| Mode | `Equal` |
| Setpoint | `1` |
| Active Delay | `0` |
| Clear Delay | `0` |
| Active Pipeline | Project-specific alarm notification pipeline |

`Rolling_Alarm` is an intermediate result and should not be used as the final hourly notification alarm.

## Adding Another Servo

1. Create another instance of the envelope detector UDT.
2. Configure `Servo_Actual_Value`, `SERVO_MIN`, and `SERVO_MAX` for the servo.
3. Adjust `Tolerance_Percent`, `Min_Outside_Samples`, and `Min_Alert_Minutes` as required.
4. Add the new instance path to the Gateway Timer Script's `detectors` list.
5. Confirm that `Detector_Status`, `Outside_Count`, `Rolling_Alarm`, `Hour_Outside_Count`, and `Hour_Alarm` update as intended.

## Troubleshooting

### Detector tags do not update

- Confirm the Gateway Timer Script is enabled.
- Confirm the Project Library resource and Gateway Timer Script are saved.
- Confirm the evaluator call matches the Project Library package and script structure.
- Review the Gateway logs for `EnvelopeDetector` and `EnvelopeDetectorTimer` entries.

### Detector reports bad quality

- Check the quality of `Servo_Actual_Value`, `SERVO_MIN`, and `SERVO_MAX`.
- Verify that each reference or expression path resolves to an existing tag.
- Do not bypass the quality check, because invalid envelope inputs can produce false anomaly results.

### Email notification fails

If the alarm and notification pipeline activate but no email arrives, review the Gateway logs for SMTP errors. A connection timeout indicates that the Gateway could not establish a connection to the configured SMTP host and port; this is separate from the envelope-detection logic.

## Repository

Project repository: [AJG-ACE/Ignition-Envelope-Detector](https://github.com/AJG-ACE/Ignition-Envelope-Detector)

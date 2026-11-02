def evaluate(basePath):
    """
    Evaluates one operational-envelope detector instance.

    Stage 1:
        Counts outside-envelope evaluations in a rolling sample window.

    Stage 2:
        Counts abnormal completed minutes in a rolling 60-minute window.

    Reporting:
        Generates one Hourly_Alert_Pulse for each completed clock hour
        that meets Min_Alert_Minutes.

    Args:
        basePath:
            Fully qualified path to the detector UDT instance.

    Returns:
        True if evaluation completes successfully.
        False if validation, read, or write failures occur.
    """

    logger = system.util.getLogger("EnvelopeDetector")

    try:
        # --------------------------------------------------------
        # NORMALIZE BASE PATH
        # --------------------------------------------------------

        basePath = str(basePath).rstrip("/")

        if not basePath:
            logger.error(
                "Detector called with an empty basePath."
            )
            return False

        # --------------------------------------------------------
        # TAG PATHS
        # --------------------------------------------------------

        actualPath = basePath + "/Servo_Actual_Value"
        lowerPath = basePath + "/SERVO_MIN"
        upperPath = basePath + "/SERVO_MAX"

        tolerancePath = basePath + "/Tolerance_Percent"
        windowSecondsPath = basePath + "/Window_Seconds"
        sampleIntervalPath = basePath + "/Sample_Interval_Seconds"
        minimumOutsidePath = basePath + "/Min_Outside_Samples"

        outsideHistoryPath = basePath + "/Outside_History"
        outsideCountPath = basePath + "/Outside_Count"
        rollingAlarmPath = basePath + "/Rolling_Alarm"

        hourHistoryPath = basePath + "/Hour_History"
        hourOutsideCountPath = basePath + "/Hour_Outside_Count"
        minimumAlertMinutesPath = basePath + "/Min_Alert_Minutes"
        hourAlarmPath = basePath + "/Hour_Alarm"

        currentHourOutsideCountPath = (
            basePath + "/Current_Hour_Outside_Count"
        )

        lastHourKeyPath = basePath + "/Last_Hour_Key"
        hourlyAlertPulsePath = basePath + "/Hourly_Alert_Pulse"

        lastMinuteKeyPath = basePath + "/Last_Minute_Key"
        lastMinuteResultPath = basePath + "/Last_Minute_Result"

        detectorStatusPath = basePath + "/Detector_Status"

        # --------------------------------------------------------
        # READ INPUTS AND SAVED STATE
        # --------------------------------------------------------

        readPaths = [
            actualPath,
            lowerPath,
            upperPath,
            tolerancePath,
            windowSecondsPath,
            sampleIntervalPath,
            minimumOutsidePath,
            outsideHistoryPath,
            hourHistoryPath,
            minimumAlertMinutesPath,
            lastMinuteKeyPath,
            lastMinuteResultPath,
            currentHourOutsideCountPath,
            lastHourKeyPath
        ]

        values = system.tag.readBlocking(readPaths)

        # --------------------------------------------------------
        # VERIFY READ COUNT
        # --------------------------------------------------------

        if len(values) != len(readPaths):
            status = (
                "Read count mismatch: expected %d, received %d"
                % (
                    len(readPaths),
                    len(values)
                )
            )

            logger.error(
                "%s | Detector=%s"
                % (
                    status,
                    basePath
                )
            )

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    hourlyAlertPulsePath,
                    detectorStatusPath
                ],
                [
                    False,
                    False,
                    False,
                    status
                ]
            )

            return False

        # --------------------------------------------------------
        # QUALITY CHECK
        # --------------------------------------------------------

        badQualityDetails = []

        for index in range(len(values)):
            if not values[index].quality.isGood():
                badQualityDetails.append(
                    "%s=%s"
                    % (
                        readPaths[index],
                        values[index].quality
                    )
                )

        if badQualityDetails:
            status = (
                "Skipped: bad quality | %s"
                % " | ".join(badQualityDetails)
            )

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    hourlyAlertPulsePath,
                    detectorStatusPath
                ],
                [
                    False,
                    False,
                    False,
                    status
                ]
            )


            logger.warn(
                "%s | Detector=%s"
                % (
                    status,
                    basePath
                )
            )

            return False

        # --------------------------------------------------------
        # CONVERT VALUES
        # --------------------------------------------------------

        actual = float(values[0].value)
        lower = float(values[1].value)
        upper = float(values[2].value)

        tolerancePercent = float(values[3].value)
        windowSeconds = float(values[4].value)
        sampleIntervalSeconds = float(values[5].value)

        minimumOutsideSamples = int(values[6].value)

        outsideHistoryText = str(
            values[7].value or ""
        )

        hourHistoryText = str(
            values[8].value or ""
        )

        minimumAlertMinutes = int(values[9].value)

        lastMinuteKey = long(
            values[10].value or 0
        )

        lastMinuteResult = bool(
            values[11].value
        )

        currentHourOutsideCount = int(
            values[12].value or 0
        )

        lastHourKey = long(
            values[13].value or 0
        )

        # --------------------------------------------------------
        # CONFIGURATION VALIDATION
        # --------------------------------------------------------

        if upper <= lower:
            status = (
                "Invalid envelope: SERVO_MAX must exceed SERVO_MIN"
            )

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    hourlyAlertPulsePath,
                    detectorStatusPath
                ],
                [
                    False,
                    False,
                    False,
                    status
                ]
            )

            logger.warn(
                "%s | Detector=%s | MIN=%s | MAX=%s"
                % (
                    status,
                    basePath,
                    lower,
                    upper
                )
            )

            return False

        if tolerancePercent < 0:
            status = (
                "Invalid Tolerance_Percent: "
                "value cannot be negative"
            )

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    hourlyAlertPulsePath,
                    detectorStatusPath
                ],
                [
                    False,
                    False,
                    False,
                    status
                ]
            )

            logger.warn(
                "%s | Detector=%s"
                % (
                    status,
                    basePath
                )
            )

            return False

        if windowSeconds <= 0 or sampleIntervalSeconds <= 0:
            status = (
                "Invalid window configuration: "
                "window=%s interval=%s"
                % (
                    windowSeconds,
                    sampleIntervalSeconds
                )
            )

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    hourlyAlertPulsePath,
                    detectorStatusPath
                ],
                [
                    False,
                    False,
                    False,
                    status
                ]
            )

            logger.warn(
                "%s | Detector=%s"
                % (
                    status,
                    basePath
                )
            )

            return False

        windowSize = max(
            1,
            int(
                round(
                    windowSeconds
                    / sampleIntervalSeconds
                )
            )
        )

        if minimumOutsideSamples <= 0:
            status = (
                "Invalid Min_Outside_Samples: "
                "value must exceed zero"
            )

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    hourlyAlertPulsePath,
                    detectorStatusPath
                ],
                [
                    False,
                    False,
                    False,
                    status
                ]
            )

            logger.warn(
                "%s | Detector=%s"
                % (
                    status,
                    basePath
                )
            )

            return False

        if minimumOutsideSamples > windowSize:
            status = (
                "Invalid Min_Outside_Samples: "
                "%d exceeds window size %d"
                % (
                    minimumOutsideSamples,
                    windowSize
                )
            )

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    hourlyAlertPulsePath,
                    detectorStatusPath
                ],
                [
                    False,
                    False,
                    False,
                    status
                ]
            )

            logger.warn(
                "%s | Detector=%s"
                % (
                    status,
                    basePath
                )
            )

            return False

        if (
            minimumAlertMinutes <= 0
            or minimumAlertMinutes > 60
        ):
            status = (
                "Invalid Min_Alert_Minutes: "
                "value must be between 1 and 60"
            )

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    hourlyAlertPulsePath,
                    detectorStatusPath
                ],
                [
                    False,
                    False,
                    False,
                    status
                ]
            )

            logger.warn(
                "%s | Detector=%s"
                % (
                    status,
                    basePath
                )
            )

            return False

        # --------------------------------------------------------
        # STAGE 1: SAMPLE-LEVEL ROLLING WINDOW
        # --------------------------------------------------------

        envelopeWidth = upper - lower
        tolerance = envelopeWidth * tolerancePercent

        effectiveLower = lower - tolerance
        effectiveUpper = upper + tolerance

        outside = (
            actual < effectiveLower
            or actual > effectiveUpper
        )

        outsideHistory = [
            item == "1"
            for item in outsideHistoryText.split(",")
            if item in ("0", "1")
        ]

        outsideHistory.append(outside)
        outsideHistory = outsideHistory[-windowSize:]

        outsideCount = sum(
            1
            for result in outsideHistory
            if result
        )

        minuteWindowReady = (
            len(outsideHistory) >= windowSize
        )

        rollingAlarm = (
            minuteWindowReady
            and outsideCount >= minimumOutsideSamples
        )

        # --------------------------------------------------------
        # RESTORE MINUTE-LEVEL HISTORY
        # --------------------------------------------------------

        hourHistory = [
            item == "1"
            for item in hourHistoryText.split(",")
            if item in ("0", "1")
        ]

        hourHistory = hourHistory[-60:]

        now = system.date.now()
        nowMillis = system.date.toMillis(now)

        currentMinuteKey = long(
            nowMillis // 60000
        )

        currentHourKey = long(
            nowMillis // 3600000
        )

        # --------------------------------------------------------
        # INITIALIZE FIXED HOUR BEFORE PROCESSING MINUTE BOUNDARY
        # --------------------------------------------------------

        if lastHourKey <= 0:
            lastHourKey = currentHourKey

        # --------------------------------------------------------
        # COMPLETED-MINUTE PROCESSING
        # --------------------------------------------------------

        if lastMinuteKey <= 0:
            lastMinuteKey = currentMinuteKey
            lastMinuteResult = rollingAlarm

        elif currentMinuteKey == lastMinuteKey:
            lastMinuteResult = (
                lastMinuteResult
                or rollingAlarm
            )

        elif currentMinuteKey > lastMinuteKey:
            # The prior minute has completed.
            completedMinuteResult = lastMinuteResult

            # Existing rolling 60-minute history.
            hourHistory.append(
                completedMinuteResult
            )

            skippedMinutes = (
                currentMinuteKey
                - lastMinuteKey
                - 1
            )

            if skippedMinutes > 0:
                skippedMinutes = min(
                    skippedMinutes,
                    60
                )

                hourHistory.extend(
                    [False] * int(skippedMinutes)
                )

            hourHistory = hourHistory[-60:]

            # Fixed clock-hour reporting counter.
            #
            # Only count the completed minute in the previous
            # fixed hour when the hour boundary has not yet been
            # processed below.
            if completedMinuteResult:
                currentHourOutsideCount += 1

            # Start tracking the new minute.
            lastMinuteKey = currentMinuteKey
            lastMinuteResult = rollingAlarm

        else:
            logger.warn(
                "Gateway clock moved backward | Detector=%s"
                % basePath
            )

            lastMinuteKey = currentMinuteKey
            lastMinuteResult = rollingAlarm

        # --------------------------------------------------------
        # EXISTING ROLLING 60-MINUTE ALARM
        # --------------------------------------------------------

        abnormalMinuteCount = sum(
            1
            for minuteResult in hourHistory
            if minuteResult
        )

        hourWindowReady = (
            len(hourHistory) >= 60
        )

        hourAlarm = (
            hourWindowReady
            and abnormalMinuteCount >= minimumAlertMinutes
        )

        # --------------------------------------------------------
        # FIXED CLOCK-HOUR REPORTING EVENT
        # --------------------------------------------------------

        # False during normal evaluations.
        # True for one timer cycle when an anomalous hour completes.
        hourlyAlertPulse = False

        if currentHourKey > lastHourKey:
            completedHourOutsideCount = (
                currentHourOutsideCount
            )

            if (
                completedHourOutsideCount
                >= minimumAlertMinutes
            ):
                hourlyAlertPulse = True

                logger.info(
                    "Hourly reporting event | "
                    "Detector=%s | "
                    "AbnormalMinutes=%d | "
                    "Threshold=%d"
                    % (
                        basePath,
                        completedHourOutsideCount,
                        minimumAlertMinutes
                    )
                )

            currentHourOutsideCount = 0
            lastHourKey = currentHourKey

        elif currentHourKey < lastHourKey:
            logger.warn(
                "Gateway clock moved backward at hour level | "
                "Detector=%s"
                % basePath
            )

            currentHourOutsideCount = 0
            lastHourKey = currentHourKey

        # --------------------------------------------------------
        # DETECTOR STATUS
        # --------------------------------------------------------

        if not minuteWindowReady:
            status = (
                "Filling minute: %d/%d samples | "
                "Actual=%.2f | "
                "Range=%.2f to %.2f | "
                "Rolling hour=%d/60 | "
                "Clock hour abnormal=%d"
                % (
                    len(outsideHistory),
                    windowSize,
                    actual,
                    effectiveLower,
                    effectiveUpper,
                    len(hourHistory),
                    currentHourOutsideCount
                )
            )

        elif not hourWindowReady:
            status = (
                "Minute=%s (%d/%d outside) | "
                "Filling rolling hour=%d/60 | "
                "Rolling abnormal=%d | "
                "Clock hour abnormal=%d"
                % (
                    (
                        "ALERT"
                        if rollingAlarm
                        else "Normal"
                    ),
                    outsideCount,
                    windowSize,
                    len(hourHistory),
                    abnormalMinuteCount,
                    currentHourOutsideCount
                )
            )

        elif hourAlarm:
            status = (
                "HOUR ALARM: %d/60 rolling abnormal | "
                "Threshold=%d | "
                "Current minute=%s | "
                "Clock hour abnormal=%d"
                % (
                    abnormalMinuteCount,
                    minimumAlertMinutes,
                    (
                        "ALERT"
                        if rollingAlarm
                        else "Normal"
                    ),
                    currentHourOutsideCount
                )
            )

        else:
            status = (
                "Hour normal: %d/60 rolling abnormal | "
                "Threshold=%d | "
                "Current minute=%s | "
                "Clock hour abnormal=%d"
                % (
                    abnormalMinuteCount,
                    minimumAlertMinutes,
                    (
                        "ALERT"
                        if rollingAlarm
                        else "Normal"
                    ),
                    currentHourOutsideCount
                )
            )

        # --------------------------------------------------------
        # WRITE RESULT TAGS
        # --------------------------------------------------------

        writePaths = [
            outsideHistoryPath,
            outsideCountPath,
            rollingAlarmPath,
            hourHistoryPath,
            hourOutsideCountPath,
            hourAlarmPath,
            currentHourOutsideCountPath,
            lastHourKeyPath,
            hourlyAlertPulsePath,
            lastMinuteKeyPath,
            lastMinuteResultPath,
            detectorStatusPath
        ]

        writeValues = [
            ",".join(
                "1" if result else "0"
                for result in outsideHistory
            ),
            outsideCount,
            rollingAlarm,
            ",".join(
                "1" if minuteResult else "0"
                for minuteResult in hourHistory
            ),
            abnormalMinuteCount,
            hourAlarm,
            currentHourOutsideCount,
            lastHourKey,
            hourlyAlertPulse,
            lastMinuteKey,
            lastMinuteResult,
            status
        ]

        writeResults = system.tag.writeBlocking(
            writePaths,
            writeValues
        )

        writeSucceeded = True

        for index in range(len(writeResults)):
            if not writeResults[index].isGood():
                writeSucceeded = False

                logger.error(
                    "Write failed | "
                    "Detector=%s | "
                    "Tag=%s | "
                    "Result=%s"
                    % (
                        basePath,
                        writePaths[index],
                        writeResults[index]
                    )
                )

        return writeSucceeded

    except Exception as error:
        errorMessage = (
            "Detector error: %s"
            % str(error)
        )

        logger.error(
            "%s | Detector=%s"
            % (
                errorMessage,
                str(basePath)
            )
        )

        try:
            system.tag.writeBlocking(
                [
                    str(basePath) + "/Rolling_Alarm",
                    str(basePath) + "/Hour_Alarm",
                    str(basePath) + "/Hourly_Alert_Pulse",
                    str(basePath) + "/Detector_Status"
                ],
                [
                    False,
                    False,
                    False,
                    errorMessage
                ]
            )

        except Exception as writeError:
            logger.error(
                "Could not write failure state | "
                "Detector=%s | Error=%s"
                % (
                    str(basePath),
                    str(writeError)
                )
            )

        return False

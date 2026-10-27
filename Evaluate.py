def evaluate(basePath):
    """
    Evaluates one operational-envelope detector instance.

    First stage:
        Counts outside-envelope evaluations in a rolling sample window.

    Second stage:
        Counts abnormal completed minutes in a rolling 60-minute window.

    Args:
        basePath:
            Fully qualified path to the detector folder or UDT instance.

            Example:
            [default]Anomaly_Detection/Line_4_Palletizer/M_12_End_Compression

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
            logger.error("Detector called with an empty basePath.")
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
            lastMinuteResultPath
        ]

        values = system.tag.readBlocking(readPaths)

        # --------------------------------------------------------
        # VERIFY READ COUNT
        # --------------------------------------------------------

        if len(values) != len(readPaths):
            status = (
                "Read count mismatch: expected %d values, received %d"
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
                    detectorStatusPath
                ],
                [
                    False,
                    False,
                    status
                ]
            )

            return False

        # --------------------------------------------------------
        # QUALITY CHECK
        # --------------------------------------------------------

        badQualityPaths = []

        for index in range(len(values)):
            if not values[index].quality.isGood():
                badQualityPaths.append(readPaths[index])

        if badQualityPaths:
            status = (
                "Skipped: bad quality on %s"
                % ", ".join(badQualityPaths)
            )

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    detectorStatusPath
                ],
                [
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
        # CONVERT INPUT VALUES
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

        # --------------------------------------------------------
        # CONFIGURATION VALIDATION
        # --------------------------------------------------------

        if upper <= lower:
            status = "Invalid envelope: MAX must exceed MIN"

            system.tag.writeBlocking(
                [
                    rollingAlarmPath,
                    hourAlarmPath,
                    detectorStatusPath
                ],
                [
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
                    detectorStatusPath
                ],
                [
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
                    detectorStatusPath
                ],
                [
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

        # Calculate the number of evaluations in the short window.
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
                    detectorStatusPath
                ],
                [
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
                    detectorStatusPath
                ],
                [
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
                    detectorStatusPath
                ],
                [
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
        # FIRST WINDOW: SAMPLE-LEVEL EVALUATION
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

        # Retain only the latest configured number of samples.
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
        # SECOND WINDOW: MINUTE-LEVEL EVALUATION
        # --------------------------------------------------------

        hourHistory = [
            item == "1"
            for item in hourHistoryText.split(",")
            if item in ("0", "1")
        ]

        # Correct a previously oversized history.
        hourHistory = hourHistory[-60:]

        now = system.date.now()

        # Unique integer for the current clock minute.
        currentMinuteKey = long(
            system.date.toMillis(now) // 60000
        )

        if lastMinuteKey <= 0:
            # First evaluation after deployment or state reset.
            lastMinuteKey = currentMinuteKey
            lastMinuteResult = rollingAlarm

        elif currentMinuteKey == lastMinuteKey:
            # Still within the current clock minute.
            #
            # If Rolling_Alarm becomes true once during the minute,
            # preserve true for the completed-minute result.
            lastMinuteResult = (
                lastMinuteResult
                or rollingAlarm
            )

        elif currentMinuteKey > lastMinuteKey:
            # A new minute has started.
            #
            # Record exactly one result for the minute that just ended.
            hourHistory.append(lastMinuteResult)

            # If the project or Gateway did not execute through one or
            # more full minutes, add false entries for those missing
            # clock-minute buckets.
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

            # Begin accumulating the new minute.
            lastMinuteKey = currentMinuteKey
            lastMinuteResult = rollingAlarm

        else:
            # System clock moved backward.
            logger.warn(
                "Gateway clock moved backward | Detector=%s"
                % basePath
            )

            lastMinuteKey = currentMinuteKey
            lastMinuteResult = rollingAlarm

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
        # DETECTOR STATUS
        # --------------------------------------------------------

        if not minuteWindowReady:
            status = (
                "Filling minute: %d/%d samples | "
                "Actual=%.2f | Range=%.2f to %.2f | "
                "Hour=%d/60 minutes"
                % (
                    len(outsideHistory),
                    windowSize,
                    actual,
                    effectiveLower,
                    effectiveUpper,
                    len(hourHistory)
                )
            )

        elif not hourWindowReady:
            status = (
                "Minute=%s (%d/%d outside) | "
                "Filling hour=%d/60 | "
                "Abnormal minutes=%d"
                % (
                    (
                        "ALERT"
                        if rollingAlarm
                        else "Normal"
                    ),
                    outsideCount,
                    windowSize,
                    len(hourHistory),
                    abnormalMinuteCount
                )
            )

        elif hourAlarm:
            status = (
                "HOUR ALARM: %d/60 abnormal minutes | "
                "Threshold=%d | Current minute=%s"
                % (
                    abnormalMinuteCount,
                    minimumAlertMinutes,
                    (
                        "ALERT"
                        if rollingAlarm
                        else "Normal"
                    )
                )
            )

        else:
            status = (
                "Hour normal: %d/60 abnormal minutes | "
                "Threshold=%d | Current minute=%s"
                % (
                    abnormalMinuteCount,
                    minimumAlertMinutes,
                    (
                        "ALERT"
                        if rollingAlarm
                        else "Normal"
                    )
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
                    "Write failed | Detector=%s | Tag=%s | Result=%s"
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
                basePath
            )
        )

        try:
            system.tag.writeBlocking(
                [
                    basePath + "/Rolling_Alarm",
                    basePath + "/Hour_Alarm",
                    basePath + "/Detector_Status"
                ],
                [
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
                    basePath,
                    str(writeError)
                )
            )

        return False

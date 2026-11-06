# ================================================================
# ENVELOPE DETECTION REPORTING
# Ignition 8.1 / Jython 2.7 compatible
# ================================================================

# ----------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------

JOURNAL_NAME = "Envelope_Alerts"
SOURCE_TEXT_REQUIRED = "Anomaly_Detection"
FINAL_ALARM_TAG_NAME = "Hourly_Alert_Pulse"

QUALITY_ALARM_TAG_NAME = "Input_Bad_Quality"
QUALITY_ALARM_NAME = "Input_Bad_Quality_Event"
QUALITY_LOOKBACK_DAYS = 30

EMAIL_PROFILE = "DPSG notifications"
FROM_ADDRESS = "ignition-alerts@kdrp.com"

REPORT_RECIPIENTS = [
    "ashur.george@kdrp.com"
]

LOGGER_NAME = "EnvelopeReports"


# ----------------------------------------------------------------
# BASIC HELPERS
# ----------------------------------------------------------------

def _logger():
    return system.util.getLogger(LOGGER_NAME)


def _end_exclusive(startOfNextPeriod):
    return system.date.addMillis(startOfNextPeriod, -1)


def _format_date(dateValue):
    return system.date.format(dateValue, "EEEE, MMMM d, yyyy")


def _format_short_date(dateValue):
    return system.date.format(dateValue, "yyyy-MM-dd")


def _format_week_range(startDate, endExclusiveDate):
    lastDay = system.date.addDays(endExclusiveDate, -1)

    return "%s through %s" % (
        system.date.format(startDate, "MMM d, yyyy"),
        system.date.format(lastDay, "MMM d, yyyy")
    )


def _event_text(event):
    try:
        source = str(event.getSource())
    except:
        try:
            source = str(event.get("source"))
        except:
            source = ""

    try:
        displayPath = str(event.getDisplayPath())
    except:
        try:
            displayPath = str(event.get("displayPath"))
        except:
            displayPath = ""

    try:
        label = str(event.getLabel())
    except:
        try:
            label = str(event.get("label"))
        except:
            label = ""

    return "%s | %s | %s" % (
        source,
        displayPath,
        label
    )


def _event_source(event):
    try:
        return str(event.getSource())
    except:
        try:
            return str(event.get("source"))
        except:
            return ""


def _event_time(event):
    try:
        value = event.get("eventTime")
        if value is not None:
            return value
    except:
        pass

    try:
        activeData = event.getActiveData()
        if activeData is not None:
            return activeData.getTimestamp()
    except:
        pass

    return None


def _event_id(event):
    try:
        return str(event.getId())
    except:
        return "%s|%s" % (
            _event_source(event),
            str(_active_time(event))
        )


# ----------------------------------------------------------------
# EQUIPMENT NAME
# ----------------------------------------------------------------

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
        # Preserve the exact UDT instance name.
        return sourceParts[-2]

    return "Unknown_Equipment"


# ----------------------------------------------------------------
# ALARM EVENT TIME HELPERS
# ----------------------------------------------------------------

def _active_time(event):
    try:
        activeData = event.getActiveData()
        if activeData is not None:
            return activeData.getTimestamp()
    except:
        pass

    try:
        return event.get("activeTime")
    except:
        return None


def _clear_time(event):
    try:
        clearData = event.getClearedData()
        if clearData is not None:
            return clearData.getTimestamp()
    except:
        pass

    try:
        return event.get("clearTime")
    except:
        return None


def _is_quality_event(event):
    text = _event_text(event)

    return (
        QUALITY_ALARM_TAG_NAME in text
        or QUALITY_ALARM_NAME in text
    )


# ----------------------------------------------------------------
# JOURNAL QUERIES
# ----------------------------------------------------------------

def _query_active_events(startDate, endExclusiveDate):
    endDate = _end_exclusive(endExclusiveDate)

    results = system.alarm.queryJournal(
        startDate=startDate,
        endDate=endDate,
        journalName=JOURNAL_NAME,
        state=[0],
        includeSystem=False,
        includeShelved=False
    )

    events = []

    for event in results:
        searchableText = _event_text(event)

        if SOURCE_TEXT_REQUIRED not in searchableText:
            continue

        if FINAL_ALARM_TAG_NAME not in searchableText:
            continue

        events.append(event)

    return events


def _query_quality_events(periodStart, periodEnd):
    queryStart = system.date.addDays(
        periodStart,
        -QUALITY_LOOKBACK_DAYS
    )

    results = system.alarm.queryJournal(
        startDate=queryStart,
        endDate=periodEnd,
        journalName=JOURNAL_NAME,
        includeSystem=False,
        includeShelved=False
    )

    eventsById = {}

    for event in results:
        if not _is_quality_event(event):
            continue

        eventId = _event_id(event)

        if eventId not in eventsById:
            eventsById[eventId] = event
        else:
            # Prefer the version containing clear data when duplicate
            # lifecycle rows are returned for the same alarm event.
            existingClear = _clear_time(eventsById[eventId])
            candidateClear = _clear_time(event)

            if existingClear is None and candidateClear is not None:
                eventsById[eventId] = event

    return list(eventsById.values())


# ----------------------------------------------------------------
# QUALITY / AVAILABILITY CALCULATIONS
# ----------------------------------------------------------------

def _overlap_millis(
    intervalStart,
    intervalEnd,
    periodStart,
    periodEnd
):
    if intervalStart is None:
        return 0

    if intervalEnd is None:
        intervalEnd = periodEnd

    startMillis = max(
        system.date.toMillis(intervalStart),
        system.date.toMillis(periodStart)
    )

    endMillis = min(
        system.date.toMillis(intervalEnd),
        system.date.toMillis(periodEnd)
    )

    return max(0, endMillis - startMillis)


def _quality_summary(periodStart, periodEnd):
    events = _query_quality_events(
        periodStart,
        periodEnd
    )

    periodMillis = max(
        1,
        system.date.toMillis(periodEnd)
        - system.date.toMillis(periodStart)
    )

    byEquipmentMillis = {}

    for event in events:
        overlapMillis = _overlap_millis(
            _active_time(event),
            _clear_time(event),
            periodStart,
            periodEnd
        )

        if overlapMillis <= 0:
            continue

        equipment = _equipment_name(event)

        byEquipmentMillis[equipment] = (
            byEquipmentMillis.get(equipment, 0)
            + overlapMillis
        )

    rows = []

    for equipment, badMillis in byEquipmentMillis.items():
        badMinutes = float(badMillis) / 60000.0
        badHours = float(badMillis) / 3600000.0
        badPercent = (
            float(badMillis)
            / float(periodMillis)
        ) * 100.0

        rows.append({
            "equipment": equipment,
            "badMillis": badMillis,
            "badMinutes": badMinutes,
            "badHours": badHours,
            "badPercent": min(100.0, badPercent)
        })

    rows.sort(
        key=lambda row: (
            -row["badMillis"],
            row["equipment"]
        )
    )

    return {
        "rows": rows
    }


def _format_duration(badMinutes):
    totalMinutes = int(round(badMinutes))
    hours = totalMinutes // 60
    minutes = totalMinutes % 60

    if hours > 0:
        return "%dh %02dm" % (
            hours,
            minutes
        )

    return "%dm" % minutes


# ----------------------------------------------------------------
# COUNTING AND GROUPING
# ----------------------------------------------------------------

def _count_by_equipment(events):
    counts = {}

    for event in events:
        equipment = _equipment_name(event)
        counts[equipment] = counts.get(equipment, 0) + 1

    return counts


def _count_by_day(events, startDate, numberOfDays):
    countsByDate = {}

    for event in events:
        eventTime = _event_time(event)

        if eventTime is None:
            continue

        dateKey = system.date.format(
            eventTime,
            "yyyy-MM-dd"
        )

        countsByDate[dateKey] = (
            countsByDate.get(dateKey, 0) + 1
        )

    rows = []

    for dayOffset in range(numberOfDays):
        currentDate = system.date.addDays(
            startDate,
            dayOffset
        )

        dateKey = system.date.format(
            currentDate,
            "yyyy-MM-dd"
        )

        rows.append({
            "date": currentDate,
            "dateKey": dateKey,
            "dayName": system.date.format(
                currentDate,
                "EEEE"
            ),
            "count": countsByDate.get(dateKey, 0)
        })

    return rows


def _sorted_equipment_rows(counts):
    rows = []

    for equipment, count in counts.items():
        rows.append({
            "equipment": equipment,
            "count": count
        })

    rows.sort(
        key=lambda row: (
            -row["count"],
            row["equipment"]
        )
    )

    return rows


# ----------------------------------------------------------------
# COMPARISON
# ----------------------------------------------------------------

def _comparison(currentCount, previousCount):
    difference = currentCount - previousCount

    result = {
        "current": currentCount,
        "previous": previousCount,
        "difference": difference,
        "percent": None,
        "direction": "unchanged",
        "plainText": "No change",
        "htmlText": "No change"
    }

    if previousCount == 0:
        if currentCount == 0:
            return result

        result["direction"] = "up"
        result["plainText"] = (
            "Up by %d alert%s, from 0 to %d"
            % (
                difference,
                "" if difference == 1 else "s",
                currentCount
            )
        )
        result["htmlText"] = (
            '<span style="color:#b42318;">'
            '&#9650; Up by %d alert%s, from 0 to %d'
            '</span>'
            % (
                difference,
                "" if difference == 1 else "s",
                currentCount
            )
        )
        return result

    percent = (
        float(difference)
        / float(previousCount)
    ) * 100.0

    result["percent"] = percent

    if difference > 0:
        result["direction"] = "up"
        result["plainText"] = (
            "Up %.1f%% (%+d alerts)"
            % (
                abs(percent),
                difference
            )
        )
        result["htmlText"] = (
            '<span style="color:#b42318;">'
            '&#9650; Up %.1f%% (%+d alerts)'
            '</span>'
            % (
                abs(percent),
                difference
            )
        )

    elif difference < 0:
        result["direction"] = "down"
        result["plainText"] = (
            "Down %.1f%% (%d alerts)"
            % (
                abs(percent),
                difference
            )
        )
        result["htmlText"] = (
            '<span style="color:#067647;">'
            '&#9660; Down %.1f%% (%d alerts)'
            '</span>'
            % (
                abs(percent),
                difference
            )
        )

    return result


# ----------------------------------------------------------------
# DATA QUALITY FORMATTING
# ----------------------------------------------------------------

def _append_quality_text(lines, report):
    lines.extend([
        "",
        "DATA QUALITY / PLC AVAILABILITY",
        "Current reporting period:"
    ])

    qualityRows = report.get("qualityRows", [])

    if qualityRows:
        for row in qualityRows:
            lines.append(
                "%s: %s bad or uncertain quality (%.1f%% of period)"
                % (
                    row["equipment"],
                    _format_duration(row["badMinutes"]),
                    row["badPercent"]
                )
            )
    else:
        lines.append("No bad-quality periods recorded.")

    comparisonRows = report.get(
        "comparisonQualityRows",
        []
    )

    if "comparisonQualityLabel" in report:
        lines.extend([
            "",
            report["comparisonQualityLabel"] + ":"
        ])

        if comparisonRows:
            for row in comparisonRows:
                lines.append(
                    "%s: %s bad or uncertain quality (%.1f%% of period)"
                    % (
                        row["equipment"],
                        _format_duration(row["badMinutes"]),
                        row["badPercent"]
                    )
                )
        else:
            lines.append("No bad-quality periods recorded.")


def _quality_html(report):
    sections = []

    currentRows = report.get("qualityRows", [])
    currentHtml = ""

    if currentRows:
        for row in currentRows:
            currentHtml += (
                "<tr>"
                "<td style='padding:6px;border-bottom:1px solid #ddd;'>%s</td>"
                "<td style='padding:6px;border-bottom:1px solid #ddd;text-align:right;'>%s</td>"
                "<td style='padding:6px;border-bottom:1px solid #ddd;text-align:right;'>%.1f%%</td>"
                "</tr>"
                % (
                    row["equipment"],
                    _format_duration(row["badMinutes"]),
                    row["badPercent"]
                )
            )
    else:
        currentHtml = (
            "<tr><td colspan='3' style='padding:6px;'>"
            "No bad-quality periods recorded."
            "</td></tr>"
        )

    sections.append(
        "<h3>Data Quality / PLC Availability</h3>"
        "<p><strong>Current reporting period</strong></p>"
        "<table style='border-collapse:collapse;min-width:560px;'>"
        "<tr>"
        "<th style='padding:6px;text-align:left;border-bottom:2px solid #666;'>Equipment</th>"
        "<th style='padding:6px;text-align:right;border-bottom:2px solid #666;'>Bad/Uncertain Duration</th>"
        "<th style='padding:6px;text-align:right;border-bottom:2px solid #666;'>Percent of Period</th>"
        "</tr>%s</table>"
        % currentHtml
    )

    if "comparisonQualityLabel" in report:
        comparisonRows = report.get(
            "comparisonQualityRows",
            []
        )
        comparisonHtml = ""

        if comparisonRows:
            for row in comparisonRows:
                comparisonHtml += (
                    "<tr>"
                    "<td style='padding:6px;border-bottom:1px solid #ddd;'>%s</td>"
                    "<td style='padding:6px;border-bottom:1px solid #ddd;text-align:right;'>%s</td>"
                    "<td style='padding:6px;border-bottom:1px solid #ddd;text-align:right;'>%.1f%%</td>"
                    "</tr>"
                    % (
                        row["equipment"],
                        _format_duration(row["badMinutes"]),
                        row["badPercent"]
                    )
                )
        else:
            comparisonHtml = (
                "<tr><td colspan='3' style='padding:6px;'>"
                "No bad-quality periods recorded."
                "</td></tr>"
            )

        sections.append(
            "<p><strong>%s</strong></p>"
            "<table style='border-collapse:collapse;min-width:560px;'>"
            "<tr>"
            "<th style='padding:6px;text-align:left;border-bottom:2px solid #666;'>Equipment</th>"
            "<th style='padding:6px;text-align:right;border-bottom:2px solid #666;'>Bad/Uncertain Duration</th>"
            "<th style='padding:6px;text-align:right;border-bottom:2px solid #666;'>Percent of Period</th>"
            "</tr>%s</table>"
            % (
                report["comparisonQualityLabel"],
                comparisonHtml
            )
        )

    return "".join(sections)


# ----------------------------------------------------------------
# SHARED REPORT FORMATTING
# ----------------------------------------------------------------

def _equipment_text(lines, equipmentRows):
    lines.extend([
        "",
        "ALERTS BY EQUIPMENT"
    ])

    if equipmentRows:
        for row in equipmentRows:
            lines.append(
                "%s: %d"
                % (
                    row["equipment"],
                    row["count"]
                )
            )
    else:
        lines.append("No alerts recorded.")


def _equipment_html(equipmentRows):
    rowsHtml = ""

    if equipmentRows:
        for row in equipmentRows:
            rowsHtml += (
                "<tr>"
                "<td style='padding:6px;border-bottom:1px solid #ddd;'>%s</td>"
                "<td style='padding:6px;border-bottom:1px solid #ddd;text-align:right;'>%d</td>"
                "</tr>"
                % (
                    row["equipment"],
                    row["count"]
                )
            )
    else:
        rowsHtml = (
            "<tr><td colspan='2' style='padding:6px;'>"
            "No alerts recorded."
            "</td></tr>"
        )

    return (
        "<h3>Alerts by Equipment</h3>"
        "<table style='border-collapse:collapse;min-width:460px;'>"
        "<tr>"
        "<th style='padding:6px;text-align:left;border-bottom:2px solid #666;'>Equipment</th>"
        "<th style='padding:6px;text-align:right;border-bottom:2px solid #666;'>Alerts</th>"
        "</tr>%s</table>"
        % rowsHtml
    )


def _daily_plain_text(report):
    lines = [
        report["title"].upper(),
        "",
        "Reporting period: %s" % report["periodLabel"],
        "",
        "%s: %d" % (
            report["currentLabel"],
            report["currentCount"]
        ),
        "%s: %d" % (
            report["previousLabel"],
            report["previousCount"]
        ),
        "Change: %s" % report["comparison"]["plainText"]
    ]

    _equipment_text(
        lines,
        report["equipmentRows"]
    )

    _append_quality_text(
        lines,
        report
    )

    return "\n".join(lines)


def _daily_html(report):
    return """
<html>
<body style="font-family:Segoe UI,Arial,sans-serif;color:#222;">
    <h2>%s</h2>
    <p><strong>Reporting period:</strong> %s</p>
    <table style="border-collapse:collapse;min-width:460px;">
        <tr><td style="padding:6px;"><strong>%s</strong></td><td style="padding:6px;text-align:right;">%d</td></tr>
        <tr><td style="padding:6px;"><strong>%s</strong></td><td style="padding:6px;text-align:right;">%d</td></tr>
        <tr><td style="padding:6px;"><strong>Change</strong></td><td style="padding:6px;text-align:right;">%s</td></tr>
    </table>
    %s
    %s
</body>
</html>
""" % (
        report["title"],
        report["periodLabel"],
        report["currentLabel"],
        report["currentCount"],
        report["previousLabel"],
        report["previousCount"],
        report["comparison"]["htmlText"],
        _equipment_html(report["equipmentRows"]),
        _quality_html(report)
    )


def _weekly_plain_text(report):
    lines = [
        report["title"].upper(),
        "",
        "Reporting period: %s" % report["periodLabel"],
        "",
        "%s: %d" % (
            report["currentLabel"],
            report["currentCount"]
        ),
        "%s: %d" % (
            report["previousLabel"],
            report["previousCount"]
        ),
        "Change: %s" % report["comparison"]["plainText"],
        "",
        "DAILY BREAKDOWN"
    ]

    for row in report["dailyRows"]:
        lines.append(
            "%s (%s): %d"
            % (
                row["dayName"],
                row["dateKey"],
                row["count"]
            )
        )

    _equipment_text(
        lines,
        report["equipmentRows"]
    )

    _append_quality_text(
        lines,
        report
    )

    return "\n".join(lines)


def _weekly_html(report):
    dailyRowsHtml = ""

    for row in report["dailyRows"]:
        dailyRowsHtml += (
            "<tr>"
            "<td style='padding:6px;border-bottom:1px solid #ddd;'>%s</td>"
            "<td style='padding:6px;border-bottom:1px solid #ddd;'>%s</td>"
            "<td style='padding:6px;border-bottom:1px solid #ddd;text-align:right;'>%d</td>"
            "</tr>"
            % (
                row["dayName"],
                row["dateKey"],
                row["count"]
            )
        )

    return """
<html>
<body style="font-family:Segoe UI,Arial,sans-serif;color:#222;">
    <h2>%s</h2>
    <p><strong>Reporting period:</strong> %s</p>
    <table style="border-collapse:collapse;min-width:460px;">
        <tr><td style="padding:6px;"><strong>%s</strong></td><td style="padding:6px;text-align:right;">%d</td></tr>
        <tr><td style="padding:6px;"><strong>%s</strong></td><td style="padding:6px;text-align:right;">%d</td></tr>
        <tr><td style="padding:6px;"><strong>Change</strong></td><td style="padding:6px;text-align:right;">%s</td></tr>
    </table>
    <h3>Daily Breakdown</h3>
    <table style="border-collapse:collapse;min-width:460px;">
        <tr>
            <th style="padding:6px;text-align:left;border-bottom:2px solid #666;">Day</th>
            <th style="padding:6px;text-align:left;border-bottom:2px solid #666;">Date</th>
            <th style="padding:6px;text-align:right;border-bottom:2px solid #666;">Alerts</th>
        </tr>
        %s
    </table>
    %s
    %s
</body>
</html>
""" % (
        report["title"],
        report["periodLabel"],
        report["currentLabel"],
        report["currentCount"],
        report["previousLabel"],
        report["previousCount"],
        report["comparison"]["htmlText"],
        dailyRowsHtml,
        _equipment_html(report["equipmentRows"]),
        _quality_html(report)
    )


# ----------------------------------------------------------------
# WEEK BOUNDARY
# ----------------------------------------------------------------

def _start_of_current_week(referenceDate):
    from java.util import Calendar

    dayStart = system.date.midnight(referenceDate)
    calendar = Calendar.getInstance()
    calendar.setTime(dayStart)

    javaDayOfWeek = calendar.get(
        Calendar.DAY_OF_WEEK
    )

    daysSinceMonday = (
        javaDayOfWeek
        - Calendar.MONDAY
        + 7
    ) % 7

    return system.date.addDays(
        dayStart,
        -daysSinceMonday
    )


# ----------------------------------------------------------------
# PUBLIC REPORT FUNCTIONS
# ----------------------------------------------------------------

def getCurrentDayReport(referenceDate=None):
    if referenceDate is None:
        referenceDate = system.date.now()

    now = referenceDate
    todayStart = system.date.midnight(now)
    yesterdayStart = system.date.addDays(todayStart, -1)

    elapsedMillis = (
        system.date.toMillis(now)
        - system.date.toMillis(todayStart)
    )

    yesterdaySameTime = system.date.fromMillis(
        system.date.toMillis(yesterdayStart)
        + elapsedMillis
    )

    todayEvents = _query_active_events(
        todayStart,
        now
    )

    yesterdayEvents = _query_active_events(
        yesterdayStart,
        yesterdaySameTime
    )

    currentQuality = _quality_summary(
        todayStart,
        now
    )

    previousQuality = _quality_summary(
        yesterdayStart,
        yesterdaySameTime
    )

    currentCount = len(todayEvents)
    previousCount = len(yesterdayEvents)

    currentTimeLabel = system.date.format(
        now,
        "h:mm a"
    )

    report = {
        "reportType": "currentDay",
        "title": "Current-Day Operational Envelope Report",
        "periodStart": todayStart,
        "periodEnd": now,
        "comparisonStart": yesterdayStart,
        "comparisonEnd": yesterdaySameTime,
        "periodLabel": "%s, midnight through %s" % (
            _format_date(todayStart),
            currentTimeLabel
        ),
        "currentLabel": "Alerts today through %s" % currentTimeLabel,
        "previousLabel": "Alerts yesterday through %s" % currentTimeLabel,
        "currentCount": currentCount,
        "previousCount": previousCount,
        "comparison": _comparison(currentCount, previousCount),
        "equipmentRows": _sorted_equipment_rows(
            _count_by_equipment(todayEvents)
        ),
        "qualityRows": currentQuality["rows"],
        "comparisonQualityRows": previousQuality["rows"],
        "comparisonQualityLabel": "Yesterday through the same time"
    }

    report["subject"] = (
        "Current-Day Envelope Report - %s through %s"
        % (
            _format_short_date(todayStart),
            currentTimeLabel
        )
    )
    report["text"] = _daily_plain_text(report)
    report["html"] = _daily_html(report)

    return report


def getDailyReport(referenceDate=None):
    if referenceDate is None:
        referenceDate = system.date.now()

    todayStart = system.date.midnight(referenceDate)
    yesterdayStart = system.date.addDays(todayStart, -1)
    previousDayStart = system.date.addDays(todayStart, -2)

    yesterdayEvents = _query_active_events(
        yesterdayStart,
        todayStart
    )

    previousDayEvents = _query_active_events(
        previousDayStart,
        yesterdayStart
    )

    currentQuality = _quality_summary(
        yesterdayStart,
        todayStart
    )

    previousQuality = _quality_summary(
        previousDayStart,
        yesterdayStart
    )

    currentCount = len(yesterdayEvents)
    previousCount = len(previousDayEvents)

    report = {
        "reportType": "daily",
        "title": "Daily Operational Envelope Report",
        "periodStart": yesterdayStart,
        "periodEnd": todayStart,
        "comparisonStart": previousDayStart,
        "comparisonEnd": yesterdayStart,
        "periodLabel": _format_date(yesterdayStart),
        "currentLabel": "Alerts yesterday",
        "previousLabel": "Alerts previous day",
        "currentCount": currentCount,
        "previousCount": previousCount,
        "comparison": _comparison(currentCount, previousCount),
        "equipmentRows": _sorted_equipment_rows(
            _count_by_equipment(yesterdayEvents)
        ),
        "qualityRows": currentQuality["rows"],
        "comparisonQualityRows": previousQuality["rows"],
        "comparisonQualityLabel": "Previous calendar day"
    }

    report["subject"] = (
        "Daily Envelope Report - %s"
        % _format_short_date(yesterdayStart)
    )
    report["text"] = _daily_plain_text(report)
    report["html"] = _daily_html(report)

    return report


def getWeeklyReport(referenceDate=None):
    if referenceDate is None:
        referenceDate = system.date.now()

    currentWeekStart = _start_of_current_week(referenceDate)
    reportingWeekStart = system.date.addWeeks(currentWeekStart, -1)
    previousWeekStart = system.date.addWeeks(currentWeekStart, -2)

    reportingWeekEvents = _query_active_events(
        reportingWeekStart,
        currentWeekStart
    )

    previousWeekEvents = _query_active_events(
        previousWeekStart,
        reportingWeekStart
    )

    currentQuality = _quality_summary(
        reportingWeekStart,
        currentWeekStart
    )

    previousQuality = _quality_summary(
        previousWeekStart,
        reportingWeekStart
    )

    currentCount = len(reportingWeekEvents)
    previousCount = len(previousWeekEvents)

    report = {
        "reportType": "weekly",
        "title": "Weekly Operational Envelope Report",
        "periodStart": reportingWeekStart,
        "periodEnd": currentWeekStart,
        "comparisonStart": previousWeekStart,
        "comparisonEnd": reportingWeekStart,
        "periodLabel": _format_week_range(
            reportingWeekStart,
            currentWeekStart
        ),
        "currentLabel": "Alerts this reporting week",
        "previousLabel": "Alerts previous week",
        "currentCount": currentCount,
        "previousCount": previousCount,
        "comparison": _comparison(currentCount, previousCount),
        "dailyRows": _count_by_day(
            reportingWeekEvents,
            reportingWeekStart,
            7
        ),
        "equipmentRows": _sorted_equipment_rows(
            _count_by_equipment(reportingWeekEvents)
        ),
        "qualityRows": currentQuality["rows"],
        "comparisonQualityRows": previousQuality["rows"],
        "comparisonQualityLabel": "Previous completed week"
    }

    report["subject"] = (
        "Weekly Envelope Report - %s"
        % report["periodLabel"]
    )
    report["text"] = _weekly_plain_text(report)
    report["html"] = _weekly_html(report)

    return report


def getWeekToDateReport(referenceDate=None):
    from java.util import Calendar

    if referenceDate is None:
        referenceDate = system.date.now()

    now = referenceDate
    currentWeekStart = _start_of_current_week(now)
    previousWeekStart = system.date.addWeeks(currentWeekStart, -1)

    elapsedMillis = (
        system.date.toMillis(now)
        - system.date.toMillis(currentWeekStart)
    )

    previousWeekEquivalentEnd = system.date.fromMillis(
        system.date.toMillis(previousWeekStart)
        + elapsedMillis
    )

    currentEvents = _query_active_events(
        currentWeekStart,
        now
    )

    previousEvents = _query_active_events(
        previousWeekStart,
        previousWeekEquivalentEnd
    )

    currentQuality = _quality_summary(
        currentWeekStart,
        now
    )

    previousQuality = _quality_summary(
        previousWeekStart,
        previousWeekEquivalentEnd
    )

    calendar = Calendar.getInstance()
    calendar.setTime(now)

    daysSinceMonday = (
        calendar.get(Calendar.DAY_OF_WEEK)
        - Calendar.MONDAY
        + 7
    ) % 7

    numberOfDays = daysSinceMonday + 1
    currentCount = len(currentEvents)
    previousCount = len(previousEvents)

    periodLabel = "%s through %s" % (
        system.date.format(
            currentWeekStart,
            "MMM d, yyyy"
        ),
        system.date.format(
            now,
            "MMM d, yyyy h:mm a"
        )
    )

    report = {
        "reportType": "weekToDate",
        "title": "Week-to-Date Operational Envelope Report",
        "periodStart": currentWeekStart,
        "periodEnd": now,
        "comparisonStart": previousWeekStart,
        "comparisonEnd": previousWeekEquivalentEnd,
        "periodLabel": periodLabel,
        "currentLabel": "Alerts this week to date",
        "previousLabel": "Alerts previous week to same point",
        "currentCount": currentCount,
        "previousCount": previousCount,
        "comparison": _comparison(currentCount, previousCount),
        "dailyRows": _count_by_day(
            currentEvents,
            currentWeekStart,
            numberOfDays
        ),
        "equipmentRows": _sorted_equipment_rows(
            _count_by_equipment(currentEvents)
        ),
        "qualityRows": currentQuality["rows"],
        "comparisonQualityRows": previousQuality["rows"],
        "comparisonQualityLabel": "Previous week through the same elapsed point"
    }

    report["subject"] = (
        "Week-to-Date Envelope Report - %s"
        % system.date.format(now, "yyyy-MM-dd")
    )
    report["text"] = _weekly_plain_text(report)
    report["html"] = _weekly_html(report)

    return report


# ----------------------------------------------------------------
# EMAIL FUNCTIONS
# ----------------------------------------------------------------

def _send_report(report):
    logger = _logger()

    try:
        body = report.get("html", report["text"])
        isHtml = "html" in report

        system.net.sendEmail(
            smtp="",
            smtpProfile=EMAIL_PROFILE,
            fromAddr=FROM_ADDRESS,
            to=REPORT_RECIPIENTS,
            subject=report["subject"],
            body=body,
            html=isHtml,
            timeout=30000,
            retries=1
        )

        logger.info(
            "Report email submitted successfully | Type=%s"
            % report["reportType"]
        )

        return True

    except Exception as error:
        logger.error(
            "Report email failed | Type=%s | Error=%s"
            % (
                report.get("reportType", "unknown"),
                str(error)
            )
        )

        return False


def sendCurrentDayReport(referenceDate=None):
    return _send_report(
        getCurrentDayReport(referenceDate)
    )


def sendDailyReport(referenceDate=None):
    return _send_report(
        getDailyReport(referenceDate)
    )


def sendWeekToDateReport(referenceDate=None):
    return _send_report(
        getWeekToDateReport(referenceDate)
    )


def sendWeeklyReport(referenceDate=None):
    return _send_report(
        getWeeklyReport(referenceDate)
    )

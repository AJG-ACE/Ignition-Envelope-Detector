# ================================================================
# ENVELOPE DETECTION REPORTING
#
# Project Library script name:
#     envelopeReports
#
# Public functions:
#     getDailyReport()
#     getWeeklyReport()
#     sendDailyReport()
#     sendWeeklyReport()
#
# The daily report covers:
#     Yesterday vs. the day before yesterday
#
# The weekly report covers:
#     Last completed Monday-Sunday week
#     vs. the completed week before it
# ================================================================


# ----------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------

JOURNAL_NAME = "Envelope_Alerts"

# Because Anomaly_Journal is intended to contain only anomaly alarms,
# this filter is primarily an additional safeguard.
SOURCE_TEXT_REQUIRED = "Anomaly_Detection"

# Only final hourly alarms should count as reportable alerts.
FINAL_ALARM_TAG_NAME = "Hourly_Alert_Pulse"

# Email settings.
#
# EMAIL_PROFILE must be a Gateway SMTP Email Profile under:
# Gateway Config > Networking > Email Settings
#
# This is not necessarily the same resource as an Alarm Notification
# Profile under Alarming > Notification.
EMAIL_PROFILE = "DPSG notifications" # Insert your prefered ignition email profile here

FROM_ADDRESS = "ignition-alerts@kdrp.com" # Insert From adress here

REPORT_RECIPIENTS = [
    # Input Report Recipents Here
]

LOGGER_NAME = "EnvelopeReports"


# ----------------------------------------------------------------
# BASIC HELPERS
# ----------------------------------------------------------------

def _logger():
    return system.util.getLogger(LOGGER_NAME)


def _end_exclusive(startOfNextPeriod):
    """
    queryJournal date ranges are inclusive.

    Subtract one millisecond from the next period's start to avoid
    counting the same midnight event in two adjacent periods.
    """

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
    """
    Returns a combined searchable representation of an alarm event.
    """

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


def _event_display_path(event):
    try:
        value = str(event.getDisplayPath())

        if value:
            return value
    except:
        pass

    try:
        value = str(event.getDisplayPathOrSource())

        if value:
            return value
    except:
        pass

    return _event_source(event)


def _event_time(event):
    """
    Retrieves the historical alarm event time.
    """

    try:
        return event.get("eventTime")
    except:
        pass

    try:
        return event.getActiveData().getTimestamp()
    except:
        pass

    return None


# ----------------------------------------------------------------
# EQUIPMENT-NAME HELPERS
# ----------------------------------------------------------------

def _clean_source_path(pathText):
    """
    Converts an Ignition alarm source path into a more readable path.

    Example canonical source formats may contain sections such as:
        prov:default:/tag:Anomaly_Detection/.../Hour_Alarm:/alm:Name

    This function removes common Ignition source-path markers.
    """

    text = str(pathText or "")

    replacements = [
        ("prov:default:/tag:", ""),
        ("prov:", ""),
        (":/tag:", "/"),
        (":/alm:", "/"),
        ("[default]", "")
    ]

    for oldValue, newValue in replacements:
        text = text.replace(oldValue, newValue)

    return text.strip("/")


def _equipment_name(event):
    """
    Extracts the servo / UDT instance name from the alarm source.

    Example source:
        prov:default:/tag:Anomaly_Detection/
        Line_4_Palletizer/
        M_12_End_Compression/
        Hourly_Alert_Pulse:/
        alm:Hourly_Envelope_Event

    Returns:
        M 12 End Compression
    """

    # Prefer explicit associated data if you add it later.
    try:
        if event.contains("Equipment"):
            equipment = str(
                event.get("Equipment")
            )

            if equipment:
                return equipment
    except:
        pass

    # For these alarms, Source is preferable to DisplayPath because
    # Source contains the complete tag hierarchy.
    source = _event_source(event)

    source = str(
        source or ""
    )

    # Remove the canonical Ignition provider/tag prefix.
    prefix = "prov:default:/tag:"

    if source.startswith(prefix):
        source = source[len(prefix):]

    # Remove the alarm portion.
    #
    # Example:
    # Hourly_Alert_Pulse:/alm:Hourly_Envelope_Event
    if ":/alm:" in source:
        source = source.split(
            ":/alm:",
            1
        )[0]

    sourceParts = [
        part
        for part in source.split("/")
        if part
    ]

    # Expected structure:
    #
    # 0 = Anomaly_Detection
    # 1 = Line_4_Palletizer
    # 2 = M_12_End_Compression
    # 3 = Hourly_Alert_Pulse
    #
    # The UDT instance is therefore immediately above the
    # Hourly_Alert_Pulse member.

    if len(sourceParts) >= 2:
        equipment = sourceParts[-2]

        return equipment.replace(
            "_",
            " "
        )

    return "Unknown Equipment"

# ----------------------------------------------------------------
# JOURNAL QUERY
# ----------------------------------------------------------------

def _query_active_events(startDate, endExclusiveDate):
    """
    Queries ACTIVE envelope alarm events from Anomaly_Journal.

    Only active transitions are returned so that alarm clears and
    acknowledgements are not counted as additional anomaly events.
    """

    endDate = _end_exclusive(endExclusiveDate)

    _logger().info(
        "Querying %s from %s through %s"
        % (
            JOURNAL_NAME,
            system.date.format(
                startDate,
                "yyyy-MM-dd HH:mm:ss"
            ),
            system.date.format(
                endDate,
                "yyyy-MM-dd HH:mm:ss"
            )
        )
    )

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


# ----------------------------------------------------------------
# COUNTING AND GROUPING
# ----------------------------------------------------------------

def _count_by_equipment(events):
    counts = {}

    for event in events:
        equipment = _equipment_name(event)

        counts[equipment] = counts.get(
            equipment,
            0
        ) + 1

    return counts


def _count_by_day(events, startDate, numberOfDays):
    """
    Returns one row per requested calendar day, including days with
    zero alerts.
    """

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
            "count": countsByDate.get(
                dateKey,
                0
            )
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
# COMPARISON HELPERS
# ----------------------------------------------------------------

def _comparison(currentCount, previousCount):
    """
    Returns comparison fields without claiming an infinite percentage
    increase when the previous period had zero alerts.
    """

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
            "</span>"
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
            "&#9650; Up %.1f%% (%+d alerts)"
            "</span>"
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
            "&#9660; Down %.1f%% (%d alerts)"
            "</span>"
            % (
                abs(percent),
                difference
            )
        )

    return result


# ----------------------------------------------------------------
# DAILY REPORT FORMATTING
# ----------------------------------------------------------------

def _daily_plain_text(report):
    lines = [
        report["title"].upper(),
        "",
        "Reporting period: %s" % report["periodLabel"],
        "",
        "%s: %d"
        % (
            report["currentLabel"],
            report["currentCount"]
        ),
        "%s: %d"
        % (
            report["previousLabel"],
            report["previousCount"]
        ),
        "Change: %s"
        % report["comparison"]["plainText"],
        "",
        "ALERTS BY EQUIPMENT"
    ]

    if report["equipmentRows"]:
        for row in report["equipmentRows"]:
            lines.append(
                "%s: %d"
                % (
                    row["equipment"],
                    row["count"]
                )
            )
    else:
        lines.append("No alerts recorded.")

    return "\n".join(lines)


def _daily_html(report):
    equipmentRows = ""

    if report["equipmentRows"]:
        for row in report["equipmentRows"]:
            equipmentRows += (
                "<tr>"
                "<td style='padding:6px;"
                "border-bottom:1px solid #ddd;'>%s</td>"
                "<td style='padding:6px;"
                "border-bottom:1px solid #ddd;"
                "text-align:right;'>%d</td>"
                "</tr>"
                % (
                    row["equipment"],
                    row["count"]
                )
            )
    else:
        equipmentRows = (
            "<tr>"
            "<td colspan='2' style='padding:6px;'>"
            "No alerts recorded."
            "</td>"
            "</tr>"
        )

    return """
<html>
<body style="font-family:Segoe UI,Arial,sans-serif;color:#222;">

    <h2>%s</h2>

    <p>
        <strong>Reporting period:</strong>
        %s
    </p>

    <table style="border-collapse:collapse;min-width:460px;">
        <tr>
            <td style="padding:6px;">
                <strong>%s</strong>
            </td>
            <td style="padding:6px;text-align:right;">
                %d
            </td>
        </tr>

        <tr>
            <td style="padding:6px;">
                <strong>%s</strong>
            </td>
            <td style="padding:6px;text-align:right;">
                %d
            </td>
        </tr>

        <tr>
            <td style="padding:6px;">
                <strong>Change</strong>
            </td>
            <td style="padding:6px;text-align:right;">
                %s
            </td>
        </tr>
    </table>

    <h3>Alerts by Equipment</h3>

    <table style="border-collapse:collapse;min-width:460px;">
        <tr>
            <th style="
                padding:6px;
                text-align:left;
                border-bottom:2px solid #666;
            ">
                Equipment
            </th>

            <th style="
                padding:6px;
                text-align:right;
                border-bottom:2px solid #666;
            ">
                Alerts
            </th>
        </tr>

        %s
    </table>

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
        equipmentRows
    )


# ----------------------------------------------------------------
# WEEKLY REPORT FORMATTING
# ----------------------------------------------------------------

def _weekly_plain_text(report):
    lines = [
        "WEEKLY OPERATIONAL ENVELOPE REPORT",
        "",
        "Reporting week: %s" % report["periodLabel"],
        "",
        "Alerts this reporting week: %d" % report["currentCount"],
        "Alerts previous week: %d" % report["previousCount"],
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

    lines.extend([
        "",
        "ALERTS BY EQUIPMENT"
    ])

    if report["equipmentRows"]:
        for row in report["equipmentRows"]:
            lines.append(
                "%s: %d"
                % (
                    row["equipment"],
                    row["count"]
                )
            )
    else:
        lines.append("No alerts recorded.")

    return "\n".join(lines)


def _weekly_html(report):
    dailyRows = ""

    for row in report["dailyRows"]:
        dailyRows += (
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

    equipmentRows = ""

    if report["equipmentRows"]:
        for row in report["equipmentRows"]:
            equipmentRows += (
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
        equipmentRows = (
            "<tr><td colspan='2' style='padding:6px;'>"
            "No alerts recorded."
            "</td></tr>"
        )

    return """
<html>
<body style="font-family:Segoe UI,Arial,sans-serif;color:#222;">
    <h2>Weekly Operational Envelope Report</h2>

    <p><strong>Reporting week:</strong> %s</p>

    <table style="border-collapse:collapse;min-width:460px;">
        <tr>
            <td style="padding:6px;"><strong>Alerts this week</strong></td>
            <td style="padding:6px;text-align:right;">%d</td>
        </tr>
        <tr>
            <td style="padding:6px;"><strong>Alerts previous week</strong></td>
            <td style="padding:6px;text-align:right;">%d</td>
        </tr>
        <tr>
            <td style="padding:6px;"><strong>Change</strong></td>
            <td style="padding:6px;text-align:right;">%s</td>
        </tr>
    </table>

    <h3>Daily Breakdown</h3>

    <table style="border-collapse:collapse;min-width:460px;">
        <tr>
            <th style="padding:6px;text-align:left;border-bottom:2px solid #666;">
                Day
            </th>
            <th style="padding:6px;text-align:left;border-bottom:2px solid #666;">
                Date
            </th>
            <th style="padding:6px;text-align:right;border-bottom:2px solid #666;">
                Alerts
            </th>
        </tr>
        %s
    </table>

    <h3>Alerts by Equipment</h3>

    <table style="border-collapse:collapse;min-width:460px;">
        <tr>
            <th style="padding:6px;text-align:left;border-bottom:2px solid #666;">
                Equipment
            </th>
            <th style="padding:6px;text-align:right;border-bottom:2px solid #666;">
                Alerts
            </th>
        </tr>
        %s
    </table>
</body>
</html>
""" % (
        report["periodLabel"],
        report["currentCount"],
        report["previousCount"],
        report["comparison"]["htmlText"],
        dailyRows,
        equipmentRows
    )


# ----------------------------------------------------------------
# PUBLIC REPORT FUNCTIONS
# ----------------------------------------------------------------

def getCurrentDayReport(referenceDate=None):
    """
    Builds an in-progress report for the current calendar day.

    The current period is:
        Today at midnight through the current time.

    The comparison period is:
        Yesterday at midnight through the same elapsed time.

    Example:
        If run today at 2:30 PM:

        Current:
            Today, 12:00 AM through 2:30 PM

        Comparison:
            Yesterday, 12:00 AM through 2:30 PM
    """

    if referenceDate is None:
        referenceDate = system.date.now()

    now = referenceDate

    todayStart = system.date.midnight(now)

    yesterdayStart = system.date.addDays(
        todayStart,
        -1
    )

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

    currentCount = len(todayEvents)
    previousCount = len(yesterdayEvents)

    currentTimeLabel = system.date.format(
        now,
        "h:mm a"
    )

    periodLabel = (
        "%s, midnight through %s"
        % (
            _format_date(todayStart),
            currentTimeLabel
        )
    )

    report = {
        "reportType": "currentDay",
        "title": "Current-Day Operational Envelope Report",

        "periodStart": todayStart,
        "periodEnd": now,

        "comparisonStart": yesterdayStart,
        "comparisonEnd": yesterdaySameTime,

        "periodLabel": periodLabel,

        "currentLabel": (
            "Alerts today through %s"
            % currentTimeLabel
        ),

        "previousLabel": (
            "Alerts yesterday through %s"
            % currentTimeLabel
        ),

        "currentCount": currentCount,
        "previousCount": previousCount,

        "comparison": _comparison(
            currentCount,
            previousCount
        ),

        "equipmentRows": _sorted_equipment_rows(
            _count_by_equipment(
                todayEvents
            )
        )
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
    """
    Builds a report for the latest completed calendar day.

    Example:
        If run on October 28:

        Current period:
            October 27, 00:00 through 23:59:59

        Comparison period:
            October 26, 00:00 through 23:59:59
    """

    if referenceDate is None:
        referenceDate = system.date.now()

    todayStart = system.date.midnight(referenceDate)

    yesterdayStart = system.date.addDays(
        todayStart,
        -1
    )

    previousDayStart = system.date.addDays(
        todayStart,
        -2
    )

    yesterdayEvents = _query_active_events(
        yesterdayStart,
        todayStart
    )

    previousDayEvents = _query_active_events(
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

        "periodLabel": _format_date(
            yesterdayStart
        ),

        "currentLabel": "Alerts yesterday",
        "previousLabel": "Alerts previous day",

        "currentCount": currentCount,
        "previousCount": previousCount,

        "comparison": _comparison(
            currentCount,
            previousCount
        ),

        "equipmentRows": _sorted_equipment_rows(
            _count_by_equipment(
                yesterdayEvents
            )
        )
    }

    report["subject"] = (
        "Daily Envelope Report - %s"
        % _format_short_date(yesterdayStart)
    )

    report["text"] = _daily_plain_text(report)
    report["html"] = _daily_html(report)

    return report


def _start_of_current_week(referenceDate):
    """
    Returns midnight Monday for the week containing referenceDate.
    """

    from java.util import Calendar

    dayStart = system.date.midnight(referenceDate)

    calendar = Calendar.getInstance()
    calendar.setTime(dayStart)

    javaDayOfWeek = calendar.get(
        Calendar.DAY_OF_WEEK
    )

    # Java:
    # Sunday = 1
    # Monday = 2
    # ...
    # Saturday = 7
    #
    # Convert into days since Monday.
    daysSinceMonday = (
        javaDayOfWeek
        - Calendar.MONDAY
        + 7
    ) % 7

    return system.date.addDays(
        dayStart,
        -daysSinceMonday
    )


def getWeeklyReport(referenceDate=None):
    """
    Creates a report for the last complete Monday-Sunday week and
    compares that week against the complete week before it.
    """

    if referenceDate is None:
        referenceDate = system.date.now()

    currentWeekStart = _start_of_current_week(
        referenceDate
    )

    reportingWeekStart = system.date.addWeeks(
        currentWeekStart,
        -1
    )

    previousWeekStart = system.date.addWeeks(
        currentWeekStart,
        -2
    )

    reportingWeekEvents = _query_active_events(
        reportingWeekStart,
        currentWeekStart
    )

    previousWeekEvents = _query_active_events(
        previousWeekStart,
        reportingWeekStart
    )

    currentCount = len(reportingWeekEvents)
    previousCount = len(previousWeekEvents)

    report = {
        "reportType": "weekly",
        "periodStart": reportingWeekStart,
        "periodEnd": currentWeekStart,
        "comparisonStart": previousWeekStart,
        "comparisonEnd": reportingWeekStart,
        "periodLabel": _format_week_range(
            reportingWeekStart,
            currentWeekStart
        ),
        "currentCount": currentCount,
        "previousCount": previousCount,
        "comparison": _comparison(
            currentCount,
            previousCount
        ),
        "dailyRows": _count_by_day(
            reportingWeekEvents,
            reportingWeekStart,
            7
        ),
        "equipmentRows": _sorted_equipment_rows(
            _count_by_equipment(
                reportingWeekEvents
            )
        )
    }

    report["subject"] = (
        "Weekly Envelope Report - %s"
        % report["periodLabel"]
    )

    report["text"] = _weekly_plain_text(report)
    report["html"] = _weekly_html(report)

    return report


def getWeekToDateReport(referenceDate=None):
    """
    Builds an in-progress week-to-date report.

    Current period:
        Monday at midnight through the current date/time.

    Comparison period:
        Previous Monday at midnight through the equivalent
        weekday/time during the previous week.

    Example:
        If run Wednesday at 11:00 AM:

        Current:
            Monday 00:00 through Wednesday 11:00

        Previous:
            Previous Monday 00:00 through previous Wednesday 11:00
    """

    if referenceDate is None:
        referenceDate = system.date.now()

    now = referenceDate

    # Start of the current Monday-Sunday week.
    currentWeekStart = _start_of_current_week(
        now
    )

    # Start of previous week.
    previousWeekStart = system.date.addWeeks(
        currentWeekStart,
        -1
    )

    # Match the exact elapsed time into the week.
    elapsedMillis = (
        system.date.toMillis(now)
        - system.date.toMillis(currentWeekStart)
    )

    previousWeekEquivalentEnd = system.date.fromMillis(
        system.date.toMillis(previousWeekStart)
        + elapsedMillis
    )

    # --------------------------------------------------------
    # QUERY JOURNAL EVENTS
    # --------------------------------------------------------

    currentEvents = _query_active_events(
        currentWeekStart,
        now
    )

    previousEvents = _query_active_events(
        previousWeekStart,
        previousWeekEquivalentEnd
    )

    currentCount = len(currentEvents)
    previousCount = len(previousEvents)

    # --------------------------------------------------------
    # DAILY BREAKDOWN
    # --------------------------------------------------------

    # Determine how many calendar days of the current week
    # need to appear in the report.
    from java.util import Calendar

    calendar = Calendar.getInstance()
    calendar.setTime(now)

    javaDayOfWeek = calendar.get(
        Calendar.DAY_OF_WEEK
    )

    daysSinceMonday = (
        javaDayOfWeek
        - Calendar.MONDAY
        + 7
    ) % 7

    numberOfDays = daysSinceMonday + 1

    dailyRows = _count_by_day(
        currentEvents,
        currentWeekStart,
        numberOfDays
    )

    # --------------------------------------------------------
    # REPORT LABEL
    # --------------------------------------------------------

    periodLabel = (
        "%s through %s"
        % (
            system.date.format(
                currentWeekStart,
                "MMM d, yyyy"
            ),
            system.date.format(
                now,
                "MMM d, yyyy h:mm a"
            )
        )
    )

    comparisonLabel = (
        "%s through %s"
        % (
            system.date.format(
                previousWeekStart,
                "MMM d, yyyy"
            ),
            system.date.format(
                previousWeekEquivalentEnd,
                "MMM d, yyyy h:mm a"
            )
        )
    )

    # --------------------------------------------------------
    # BUILD REPORT
    # --------------------------------------------------------

    report = {
        "reportType": "weekToDate",

        "periodStart": currentWeekStart,
        "periodEnd": now,

        "comparisonStart": previousWeekStart,
        "comparisonEnd": previousWeekEquivalentEnd,

        "periodLabel": periodLabel,
        "comparisonLabel": comparisonLabel,

        "currentCount": currentCount,
        "previousCount": previousCount,

        "comparison": _comparison(
            currentCount,
            previousCount
        ),

        "dailyRows": dailyRows,

        "equipmentRows": _sorted_equipment_rows(
            _count_by_equipment(
                currentEvents
            )
        )
    }

    # --------------------------------------------------------
    # SUBJECT
    # --------------------------------------------------------

    report["subject"] = (
        "Week-to-Date Envelope Report - %s"
        % system.date.format(
            now,
            "yyyy-MM-dd"
        )
    )

    # --------------------------------------------------------
    # TEXT FORMAT
    # --------------------------------------------------------

    lines = [
        "WEEK-TO-DATE OPERATIONAL ENVELOPE REPORT",
        "",
        "Current period:",
        periodLabel,
        "",
        "Comparison period:",
        comparisonLabel,
        "",
        "Alerts this week to date: %d"
        % currentCount,
        "Alerts previous week to same point: %d"
        % previousCount,
        "Change: %s"
        % report["comparison"]["plainText"],
        "",
        "DAILY BREAKDOWN"
    ]

    for row in dailyRows:
        lines.append(
            "%s (%s): %d"
            % (
                row["dayName"],
                row["dateKey"],
                row["count"]
            )
        )

    lines.extend([
        "",
        "ALERTS BY EQUIPMENT"
    ])

    if report["equipmentRows"]:
        for row in report["equipmentRows"]:
            lines.append(
                "%s: %d"
                % (
                    row["equipment"],
                    row["count"]
                )
            )
    else:
        lines.append(
            "No alerts recorded."
        )

    report["text"] = "\n".join(lines)

    return report

# ----------------------------------------------------------------
# OPTIONAL EMAIL FUNCTIONS
#
# Do not use these until the SMTP connectivity issue from the
# Ignition Gateway has been resolved.
# ----------------------------------------------------------------

def _send_report(report):
    logger = _logger()

    try:
        system.net.sendEmail(
            smtp="",
            smtpProfile=EMAIL_PROFILE,
            fromAddr=FROM_ADDRESS,
            to=REPORT_RECIPIENTS,
            subject=report["subject"],
            body=report["html"],
            html=True,
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
                report["reportType"],
                str(error)
            )
        )

        return False


def sendCurrentDayReport(referenceDate=None):
    report = getCurrentDayReport(referenceDate)

    return _send_report(report)

def sendDailyReport(referenceDate=None):
    report = getDailyReport(referenceDate)

    return _send_report(report)


def sendWeeklyReport(referenceDate=None):
    report = getWeeklyReport(referenceDate)

    return _send_report(report)

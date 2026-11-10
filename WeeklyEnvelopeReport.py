from java.util import Calendar

logger = system.util.getLogger(
    "WeeklyEnvelopeReport"
)

now = system.date.now()

calendar = Calendar.getInstance()
calendar.setTime(now)

dayOfWeek = calendar.get(
    Calendar.DAY_OF_WEEK
)

hour = system.date.getHour24(now)
minute = system.date.getMinute(now)

todayKey = system.date.format(
    now,
    "yyyy-MM-dd"
)

lastSentPath = (
    "[default]Anomaly_Detection/"
    "Reporting/Last_Weekly_Report_Date"
)

lastSent = str(
    system.tag.readBlocking(
        [lastSentPath]
    )[0].value or ""
)

if (
    dayOfWeek == Calendar.MONDAY
    and hour == 0
    and minute == 10
    and lastSent != todayKey
):

    logger.info(
        "Starting scheduled weekly envelope report"
    )

    success = envelopeReports.sendWeeklyReport()

    if success:

        system.tag.writeBlocking(
            [lastSentPath],
            [todayKey]
        )

        logger.info(
            "Weekly envelope report sent successfully"
        )

    else:

        logger.error(
            "Weekly envelope report failed to send"
        )

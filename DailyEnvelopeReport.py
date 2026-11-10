logger = system.util.getLogger(
    "DailyEnvelopeReport"
)

now = system.date.now()

hour = system.date.getHour24(now)
minute = system.date.getMinute(now)

todayKey = system.date.format(
    now,
    "yyyy-MM-dd"
)

lastSentPath = (
    "[default]Anomaly_Detection/"
    "Reporting/Last_Daily_Report_Date"
)

lastSent = str(
    system.tag.readBlocking(
        [lastSentPath]
    )[0].value or ""
)

if (
    hour == 0
    and minute == 5
    and lastSent != todayKey
):

    logger.info(
        "Starting scheduled daily envelope report"
    )

    success = envelopeReports.sendDailyReport()

    if success:

        system.tag.writeBlocking(
            [lastSentPath],
            [todayKey]
        )

        logger.info(
            "Daily envelope report sent successfully"
        )

    else:

        logger.error(
            "Daily envelope report failed to send"
        )

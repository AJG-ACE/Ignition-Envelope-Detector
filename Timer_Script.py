logger = system.util.getLogger("EnvelopeDetectorTimer")

detectors = [
	"[default]Anomaly_Detection/Line_4_Palletizer/M_10_Hoist",
	"[default]Anomaly_Detection/Line_4_Palletizer/M_11_Apron",
    "[default]Anomaly_Detection/Line_4_Palletizer/M_12_End_Compression"
]

for detectorPath in detectors:
    try:
        envelopeDetector.evaluate.evaluate(detectorPath)

    except Exception as error:
        logger.error(
            "Unhandled detector error | Path=%s | Error=%s"
            % (
                detectorPath,
                str(error)
            )
        )

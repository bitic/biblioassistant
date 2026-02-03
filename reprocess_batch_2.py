import subprocess

# List of DOIs from 2026 that had abstract-only summaries (excluding the ones we already fixed or tried)
dois = [
    "10.1080/22797254.2026.2622132",
    "10.1111/1752-1688.70084",
    "10.20944/preprints202601.2237.v1",
    "10.3390/agriculture16030316",
    "10.3390/hydrology13020053",
    "10.3390/rs18030445",
    "10.4995/ia.24708",
    "10.5281/zenodo.18434017",
    "10.5281/zenodo.18444225",
    "10.5281/zenodo.18444226",
    "10.5281/zenodo.18451684",
    "10.5281/zenodo.18451685",
    "10.5424/sjar/2025234-21655"
]

for doi in dois:
    print(f"\n--- Reprocessing DOI: {doi} ---")
    try:
        subprocess.run(
            ["uv", "run", "python", "-m", "src.main", "--add-doi", doi, "--force-all"],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error processing {doi}: {e}")

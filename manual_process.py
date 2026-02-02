import sys
from datetime import datetime
from src.models import Paper
from src.extractor import Extractor
from src.synthesizer import Synthesizer
from src.filter import RelevanceFilter
from src.logger import logger

# Setup logger to see output
import logging
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

def manual_run():
    # 1. Create a dummy Paper object from a real link found earlier
    paper = Paper(
        title="Revegetation Rebalances Water Resources by Enhancing Rainwater to Increase Vegetation Carrying Capacity in China's Loess Plateau",
        link="https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2025WR040307?af=R",
        published=datetime.now(),
        source="Water Resources Research",
        abstract="Vegetation restoration on China's Loess Plateau (CLP) has significantly increased green cover but has also led to a reduction in runoff and soil moisture...",
        authors=["Alice Smith", "Bob Jones"],
        doi="10.1029/2025WR040307"
    )

    print(f"\n--- Processing Paper: {paper.title} ---")

    # 2. Test Filter
    print("\n[Step 1] Testing Relevance Filter...")
    relevance_filter = RelevanceFilter()
    is_relevant = relevance_filter.check_relevance(paper)
    print(f"Result: Relevant={is_relevant}")

    if not is_relevant:
        print("Paper deemed irrelevant. Stopping here for this test (unless we force it).")
        # Forcing it for the sake of testing downstream components
        print("FORCING relevance for testing purposes.")
    
    # 3. Test Extractor
    print("\n[Step 2] Testing PDF Extractor...")
    extractor = Extractor()
    full_text = extractor.process(paper)
    
    print(f"Extracted text length: {len(full_text)} characters")
    if len(full_text) < 100:
        print("Text too short. Using Abstract as fallback for Synthesis.")
        full_text = paper.abstract

    # 4. Test Synthesizer (Gemini CLI)
    print("\n[Step 3] Testing Synthesizer (Gemini)...")
    synthesizer = Synthesizer()
    success = synthesizer.synthesize(paper, full_text)
    
    if success:
        print(f"\nSUCCESS! Summary saved to: {paper.summary_path}")
        # Print a preview
        try:
            with open(paper.summary_path, 'r') as f:
                print("\n--- Summary Preview ---")
                print(f.read()[:500] + "...")
        except:
            pass
    else:
        print("\nFAILURE: Synthesis failed.")

if __name__ == "__main__":
    manual_run()

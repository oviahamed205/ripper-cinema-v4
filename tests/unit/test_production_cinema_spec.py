import unittest
import json
import urllib.parse
from ripper.remote_hub import CouchRemoteHandler

class TestProductionCinemaSpec(unittest.TestCase):
    def test_html_contains_all_production_layers(self):
        handler = CouchRemoteHandler.__new__(CouchRemoteHandler)
        html = handler.get_html_content()

        # Check Overlay IDs & Layer Architecture
        self.assertIn('id="overlayL1Search"', html)
        self.assertIn('id="overlayL2Results"', html)
        self.assertIn('id="overlayL3Detail"', html)
        self.assertIn('id="overlayL4Player"', html)
        self.assertIn('id="overlayL4Download"', html)
        self.assertIn('id="overlayProfile"', html)
        self.assertIn('id="sourceSheetModal"', html)

        # Check 3-way Scope Toggles
        self.assertIn('All Sites', html)
        self.assertIn('Recommended', html)
        self.assertIn('My Providers', html)

        # Check User Profile Tabs
        self.assertIn('profileTabWatchlist', html)
        self.assertIn('profileTabFavorites', html)
        self.assertIn('profileTabBookmarks', html)
        self.assertIn('profileTabProviders', html)

        # Check 5 Recommended Providers in notice & default
        self.assertIn('VegaMovies', html)
        self.assertIn('KatMovieHD', html)
        self.assertIn('CineFreak', html)
        self.assertIn('OlaMovies', html)
        self.assertIn('KMmovies', html)
        self.assertIn('new2.vegamovies.futbol', html)
        self.assertIn('new.katmoviehd.top', html)
        self.assertIn('v4.olamovies.mov', html)
        self.assertIn('kmmovies.pics', html)

        # Check Big Screenshots Gallery & Lightbox
        self.assertIn('detailScreenshotsList', html)
        self.assertIn('lightboxModal', html)
        self.assertIn('screenshot-gallery-container', html)

        # Check Custom Provider Adder UI
        self.assertIn('customProvName', html)
        self.assertIn('customProvUrl', html)
        self.assertIn('customProvIcon', html)
        self.assertIn('handleAddCustomProvider', html)

        # Check Quality & Audio Language Selectors in Source Sheet
        self.assertIn('sheetQualitySelect', html)
        self.assertIn('sheetAudioSelect', html)
        self.assertIn('sheetDirectUrlText', html)

        print("✅ HTML contains all required production spec overlays and elements!")

if __name__ == '__main__':
    unittest.main()

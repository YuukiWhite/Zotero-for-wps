import os
import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RIBBON_XML_PATH = os.path.join(REPO_ROOT, "ribbon.xml")
RIBBON_JS_PATH = os.path.join(REPO_ROOT, "js", "ribbon.js")


class TestRibbonShortcuts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(RIBBON_XML_PATH, "r", encoding="utf-8") as f:
            cls.xml_content = f.read()

        cls.xml_tree = ET.parse(RIBBON_XML_PATH)
        cls.xml_root = cls.xml_tree.getroot()

        with open(RIBBON_JS_PATH, "r", encoding="utf-8") as f:
            cls.js_content = f.read()

    def test_ribbon_xml_validity_and_namespaces(self):
        """Verify ribbon.xml is well-formed XML with customUI namespace."""
        self.assertIsNotNone(self.xml_root)
        self.assertIn("customui", self.xml_root.tag.lower())

    def test_ribbon_xml_tab_keytip(self):
        """Verify zoteroTab has keytip='Z' for natural mnemonic shortcut access."""
        ns = {"mso": "http://schemas.microsoft.com/office/2006/01/customui"}
        tab = self.xml_root.find(".//mso:tab[@id='zoteroTab']", ns)
        if tab is None:
            # Fallback searching without namespace prefix if default ns handling varies
            tab = next((elem for elem in self.xml_root.iter() if elem.attrib.get("id") == "zoteroTab"), None)
        self.assertIsNotNone(tab, "Tab 'zoteroTab' not found in ribbon.xml")
        self.assertEqual(tab.attrib.get("keytip"), "Z")

    def test_ribbon_xml_button_supertips_and_keytips(self):
        """Verify button keytips and shortcut hints in supertips."""
        buttons = {}
        for elem in self.xml_root.iter():
            btn_id = elem.attrib.get("id")
            if btn_id:
                buttons[btn_id] = elem.attrib

        # Add/Edit Citation
        self.assertIn("btnAddEditCitation", buttons)
        cit_btn = buttons["btnAddEditCitation"]
        self.assertEqual(cit_btn.get("keytip"), "C")
        self.assertIn("Alt+Z", cit_btn.get("supertip", ""))
        self.assertIn("Ctrl+Alt+C", cit_btn.get("supertip", ""))

        # Add/Edit Bib
        self.assertIn("btnAddEditBib", buttons)
        bib_btn = buttons["btnAddEditBib"]
        self.assertEqual(bib_btn.get("keytip"), "B")
        self.assertIn("Alt+B", bib_btn.get("supertip", ""))

        # Refresh
        self.assertIn("btnRefresh", buttons)
        ref_btn = buttons["btnRefresh"]
        self.assertEqual(ref_btn.get("keytip"), "R")
        self.assertIn("Alt+R", ref_btn.get("supertip", ""))

    def test_js_syntax_via_node(self):
        """Verify js/ribbon.js is valid JavaScript syntax using node -c."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary not found on system PATH")
        result = subprocess.run(
            [node_bin, "-c", RIBBON_JS_PATH],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Node syntax check failed on {RIBBON_JS_PATH}:\n{result.stderr}",
        )

    def test_js_quick_functions_defined(self):
        """Verify zc_quickAddCitation, zc_quickAddBib, and zc_quickRefresh are defined."""
        self.assertIn("function zc_quickAddCitation()", self.js_content)
        self.assertIn("function zc_quickAddBib()", self.js_content)
        self.assertIn("function zc_quickRefresh()", self.js_content)

        # Check command executions
        self.assertIn("zc_bind().command('addEditCitation')", self.js_content)
        self.assertIn("zc_bind().command('addEditBibliography')", self.js_content)
        self.assertIn("zc_bind().command('refresh')", self.js_content)
        self.assertIn("zc_clearRegistry()", self.js_content)

        # Check window exposures
        self.assertIn("window.zc_quickAddCitation = zc_quickAddCitation", self.js_content)
        self.assertIn("window.zc_quickAddBib = zc_quickAddBib", self.js_content)
        self.assertIn("window.zc_quickRefresh = zc_quickRefresh", self.js_content)

    def test_js_register_keybindings(self):
        """Verify zc_registerKeyBindings implementation and keycode bindings."""
        self.assertIn("function zc_registerKeyBindings", self.js_content)
        self.assertIn("Application.KeyBindings", self.js_content)
        self.assertIn("Application.CustomizationContext", self.js_content)

        # Check KeyBindings.Add calls for all target shortcuts
        self.assertIn('Application.KeyBindings.Add(wdKeyCategoryMacro, "zc_quickAddCitation", keyCodeAltZ)', self.js_content)
        self.assertIn('Application.KeyBindings.Add(wdKeyCategoryMacro, "zc_quickAddCitation", keyCodeCtrlAltC)', self.js_content)
        self.assertIn('Application.KeyBindings.Add(wdKeyCategoryMacro, "zc_quickAddBib", keyCodeAltB)', self.js_content)
        self.assertIn('Application.KeyBindings.Add(wdKeyCategoryMacro, "zc_quickRefresh", keyCodeAltR)', self.js_content)

        # Verify keycode values match Microsoft Word / WPS specification:
        # wdKeyAlt = 1024, wdKeyControl = 512, wdKeyShift = 256
        # wdKeyZ = 90, wdKeyB = 66, wdKeyR = 82, wdKeyC = 67
        wd_alt = 1024
        wd_ctrl = 512
        self.assertEqual(wd_alt + 90, 1114)  # Alt+Z
        self.assertEqual(wd_ctrl + wd_alt + 67, 1603)  # Ctrl+Alt+C
        self.assertEqual(wd_alt + 66, 1090)  # Alt+B
        self.assertEqual(wd_alt + 82, 1106)  # Alt+R

    def test_js_event_listeners_in_onaddinload(self):
        """Verify OnAddinLoad calls zc_registerKeyBindings and registers DocumentOpen / NewDocument listeners."""
        self.assertIn("zc_registerKeyBindings();", self.js_content)
        self.assertIn('"DocumentOpen"', self.js_content)
        self.assertIn('"NewDocument"', self.js_content)
        self.assertIn("Application.ApiEvent.AddApiEventListener", self.js_content)


if __name__ == "__main__":
    unittest.main()

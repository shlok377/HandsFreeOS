"""Unit tests for system desktop application and web destination discovery."""

import os
import tempfile
import pytest
from handsfree.os_layer.discovery import AppDiscoveryService, WebDestinationResolver


def test_desktop_file_parsing_and_app_indexing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: f"/usr/bin/{b}")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a mock .desktop file
        desktop_content = """[Desktop Entry]
Name=Super Editor
GenericName=Text Editor
Exec=superedit %F
Type=Application
Categories=Utility;TextEditor;
Keywords=code;ide;programming;
"""
        file_path = os.path.join(tmpdir, "superedit.desktop")
        with open(file_path, "w") as f:
            f.write(desktop_content)

        service = AppDiscoveryService(search_paths=[tmpdir])

        assert service.find_app("super editor") == "superedit"
        assert service.find_app("text editor") == "superedit"
        assert service.find_app("editor") == "superedit"
        assert service.find_app("programming") == "superedit"


def test_web_destination_resolver_known_services():
    resolver = WebDestinationResolver()
    
    # YouTube in browser
    dest_type, target = resolver.resolve("YouTube in my browser")
    assert dest_type == "url"
    assert target == "https://www.youtube.com"

    # WhatsApp
    dest_type, target = resolver.resolve("WhatsApp")
    assert dest_type == "url"
    assert target == "https://web.whatsapp.com"

    # Direct URL
    dest_type, target = resolver.resolve("github.com/shlok377")
    assert dest_type == "url"
    assert target == "https://github.com/shlok377"


def test_web_destination_resolver_browser_fluff_fallback():
    resolver = WebDestinationResolver()
    
    # Something unknown with explicit browser intent -> Google search fallback
    dest_type, target = resolver.resolve("quantum mechanics research in my browser")
    assert dest_type == "url"
    assert "google.com/search?q=quantum mechanics research" in target


def test_target_cleaning():
    resolver = WebDestinationResolver()
    assert resolver.clean_target("Discord app") == "Discord"
    assert resolver.clean_target("Open YouTube in my browser") == "Open YouTube"
    assert resolver.clean_target("Reddit website") == "Reddit"

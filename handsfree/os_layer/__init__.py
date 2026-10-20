"""OS interaction subsystem exports."""

from handsfree.os_layer.bezier import generate_human_trajectory
from handsfree.os_layer.hyprland import HyprlandController
from handsfree.os_layer.input_controller import AdaptiveInputController
from handsfree.os_layer.network_discovery import NetworkDiscovery
from handsfree.os_layer.screen import ScreenCapture
from handsfree.os_layer.tunnel import ReverseTunnelManager
from handsfree.os_layer.lock import SingleInstanceLock

__all__ = [
    "HyprlandController",
    "ScreenCapture",
    "generate_human_trajectory",
    "AdaptiveInputController",
    "NetworkDiscovery",
    "ReverseTunnelManager",
    "SingleInstanceLock",
]

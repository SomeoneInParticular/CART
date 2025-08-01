import qt
from slicer.ScriptedLoadableModule import *

class NoDelayProxyStyle(qt.QProxyStyle):
    """Custom proxy style that removes tooltip delays"""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == qt.QStyle.SH_ToolTip_WakeUpDelay:
            return 0  # No delay for tooltips
        return super().styleHint(hint, option, widget, returnData)

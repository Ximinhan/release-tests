import click
import logging
from oar.core.worksheet_mgr import WorksheetManager
from oar.core.advisory_mgr import AdvisoryManager
from oar.core.config_store import ConfigStore
from oar.core.notification_mgr import NotificationManager
from oar.core.const import *

logger = logging.getLogger(__name__)


@click.command()
@click.pass_context
def check_cve_tracker_bug(ctx):
    """
    Check if there is any missed CVE tracker bug
    """
    # get config store from context
    cs = ctx.obj["cs"]
    try:
        # get existing report
        report = WorksheetManager(cs).get_test_report()
        # init advisory manager
        am = AdvisoryManager(cs)
        # update task status to in progress
        report.update_task_status(LABEL_TASK_CHECK_CVE_TRACKERS, TASK_STATUS_INPROGRESS)
        # trigger push job for cdn stage targets
        cve_tracker_bugs = am.check_cve_tracker_bug()
        if cve_tracker_bugs:
            NotificationManager(cs).share_new_cve_tracker_bugs(cve_tracker_bugs)
        else:
            logger.info("no new CVE tracker bug found")
        report.update_task_status(LABEL_TASK_CHECK_CVE_TRACKERS, TASK_STATUS_PASS)
    except Exception as e:
        logger.exception("check cve tracker bug failed")
        report.update_task_status(LABEL_TASK_CHECK_CVE_TRACKERS, TASK_STATUS_FAIL)
        raise

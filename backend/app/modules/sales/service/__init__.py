"""Public API of the sales module (leads, pipelines, opportunities).

Other modules and the router import only from here.
"""

from app.modules.sales.service import gdpr, links, opportunities, reports
from app.modules.sales.service.common import Context
from app.modules.sales.service.leads import (
    LEAD_SORT,
    LeadFilters,
    archive_lead,
    assign,
    conversion_preview,
    convert,
    create_lead,
    disqualify,
    export_leads,
    get_lead,
    import_create_lead,
    list_leads,
    mark_contacted,
    organization_lead_stats,
    qualify,
    reopen,
    restore_lead,
    update_lead,
)
from app.modules.sales.service.leads import REFERENCE_LISTS as _LEAD_REFERENCE_LISTS
from app.modules.sales.service.leads import SEARCH_PROVIDERS as _LEAD_SEARCH_PROVIDERS
from app.modules.sales.service.opportunities import (
    OPPORTUNITY_SORT,
    OpportunityFilters,
    organization_archive_guard,
    organization_opportunity_stats,
)
from app.modules.sales.service.pipelines import (
    add_stage,
    delete_stage,
    get_pipeline,
    list_pipelines,
    reorder_stages,
    update_stage,
)

REFERENCE_LISTS = (*_LEAD_REFERENCE_LISTS, *opportunities.REFERENCE_LISTS)
SEARCH_PROVIDERS = (*_LEAD_SEARCH_PROVIDERS, *opportunities.SEARCH_PROVIDERS)
ORGANIZATION_STATS = (organization_lead_stats, organization_opportunity_stats)
ORGANIZATION_ARCHIVE_GUARDS = (organization_archive_guard,)
PERSONAL_DATA_PROVIDERS = (gdpr.personal_data,)
CONTACT_ANONYMIZERS = (gdpr.anonymize,)

__all__ = [
    "CONTACT_ANONYMIZERS",
    "LEAD_SORT",
    "OPPORTUNITY_SORT",
    "ORGANIZATION_ARCHIVE_GUARDS",
    "ORGANIZATION_STATS",
    "PERSONAL_DATA_PROVIDERS",
    "REFERENCE_LISTS",
    "SEARCH_PROVIDERS",
    "Context",
    "LeadFilters",
    "OpportunityFilters",
    "add_stage",
    "archive_lead",
    "assign",
    "conversion_preview",
    "convert",
    "create_lead",
    "delete_stage",
    "disqualify",
    "export_leads",
    "gdpr",
    "get_lead",
    "get_pipeline",
    "import_create_lead",
    "links",
    "list_leads",
    "list_pipelines",
    "mark_contacted",
    "opportunities",
    "qualify",
    "reopen",
    "reorder_stages",
    "reports",
    "restore_lead",
    "update_lead",
    "update_stage",
]

"""
SFR Standard Library Data Import Script (CC Part 2, v3.1 Rev 5)
Usage: execute in backend/ directory
    python -m scripts.seed_sfr_library
or:
    cd backend && python scripts/seed_sfr_library.py
"""
import asyncio
import sys
import os

# Ensure app module is discoverable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import select
from app.core.database import AsyncSessionLocal, init_db
from app.models.security import SFRLibrary

# ── CC Part 2 SFR Data (covers main classes and common components)──────────────
SFR_DATA = [
    # ── FAU: Security Audit ──────────────────────────────
    ("FAU", "Security Audit", "FAU_ARP", "Security Audit Automatic Response",
     "FAU_ARP.1", "Security alarms",
     "The TSF shall take [assignment: list of actions] upon detection of a potential security violation.",
     "FAU_ARP.1.1: The TSF shall take actions upon potential security violations.", None),

    ("FAU", "Security Audit", "FAU_GEN", "Security Audit Data Generation",
     "FAU_GEN.1", "Audit data generation",
     "The TSF shall be able to generate an audit record of the following auditable events.",
     "FAU_GEN.1.1: The TSF shall be able to generate audit records.\nFAU_GEN.1.2: The TSF shall record within each audit record.",
     None),

    ("FAU", "Security Audit", "FAU_GEN", "Security Audit Data Generation",
     "FAU_GEN.2", "User identity association",
     "For audit events resulting from actions of identified users, the TSF shall be able to associate each auditable event with the identity of the user that caused the event.",
     "FAU_GEN.2.1: User identity association.", "FAU_GEN.1"),

    ("FAU", "Security Audit", "FAU_SAA", "Security Audit Analysis",
     "FAU_SAA.1", "Potential violation analysis",
     "The TSF shall be able to apply a set of rules in monitoring the audited events and based upon these rules indicate a potential violation of the TSP.",
     "FAU_SAA.1.1-2: Potential violation analysis rules.", "FAU_GEN.1"),

    ("FAU", "Security Audit", "FAU_SAR", "Security Audit Review",
     "FAU_SAR.1", "Audit review",
     "The TSF shall provide authorised users with the capability to read all audit information from the audit records.",
     "FAU_SAR.1.1-2: Audit review capability.", "FAU_GEN.1"),

    ("FAU", "Security Audit", "FAU_STG", "Security Audit Event Storage",
     "FAU_STG.1", "Protected audit trail storage",
     "The TSF shall protect the stored audit records in the audit trail from unauthorised deletion.",
     "FAU_STG.1.1-2: Protected audit trail storage.", None),

    ("FAU", "Security Audit", "FAU_STG", "Security Audit Event Storage",
     "FAU_STG.3", "Action in case of possible audit data loss",
     "The TSF shall take actions if the audit trail exceeds a threshold.",
     "FAU_STG.3.1: Action on audit overflow.", "FAU_STG.1"),

    # ── FCO: Communication ───────────────────────────────
    ("FCO", "Communication", "FCO_NRO", "Non-repudiation of Origin",
     "FCO_NRO.1", "Selective proof of origin",
     "The TSF shall be able to generate evidence of origin for transmitted information at the request of the originator.",
     "FCO_NRO.1.1-3: Selective proof of origin.", None),

    ("FCO", "Communication", "FCO_NRR", "Non-repudiation of Receipt",
     "FCO_NRR.1", "Selective proof of receipt",
     "The TSF shall be able to generate evidence of receipt for received information at the request of the recipient.",
     "FCO_NRR.1.1-3: Selective proof of receipt.", None),

    # ── FCS: Cryptographic Support ───────────────────────
    ("FCS", "Cryptographic Support", "FCS_CKM", "Cryptographic Key Management",
     "FCS_CKM.1", "Cryptographic key generation",
     "The TSF shall generate cryptographic keys in accordance with a specified cryptographic key generation algorithm.",
     "FCS_CKM.1.1: Cryptographic key generation.", "FCS_CKM.2, FCS_COP.1"),

    ("FCS", "Cryptographic Support", "FCS_CKM", "Cryptographic Key Management",
     "FCS_CKM.2", "Cryptographic key distribution",
     "The TSF shall distribute cryptographic keys in accordance with a specified cryptographic key distribution method.",
     "FCS_CKM.2.1: Key distribution method.", "FCS_CKM.1, FCS_COP.1"),

    ("FCS", "Cryptographic Support", "FCS_CKM", "Cryptographic Key Management",
     "FCS_CKM.4", "Cryptographic key destruction",
     "The TSF shall destroy cryptographic keys in accordance with a specified cryptographic key destruction method.",
     "FCS_CKM.4.1: Key destruction method.", "FCS_CKM.1"),

    ("FCS", "Cryptographic Support", "FCS_COP", "Cryptographic Operation",
     "FCS_COP.1", "Cryptographic operation",
     "The TSF shall perform cryptographic operations in accordance with a specified cryptographic algorithm and key sizes.",
     "FCS_COP.1.1: Cryptographic operation.", "FCS_CKM.1, FCS_CKM.4"),

    # ── FDP: User Data Protection ────────────────────────
    ("FDP", "User Data Protection", "FDP_ACC", "Access Control Policy",
     "FDP_ACC.1", "Subset access control",
     "The TSF shall enforce the access control SFP on subjects, objects, and operations among subjects and objects covered by the SFP.",
     "FDP_ACC.1.1: Subset access control enforcement.", "FDP_ACF.1"),

    ("FDP", "User Data Protection", "FDP_ACC", "Access Control Policy",
     "FDP_ACC.2", "Complete access control",
     "The TSF shall enforce the access control SFP on all operations between subjects and objects covered by the SFP.",
     "FDP_ACC.2.1-2: Complete access control.", "FDP_ACF.1"),

    ("FDP", "User Data Protection", "FDP_ACF", "Access Control Functions",
     "FDP_ACF.1", "Security attribute based access control",
     "The TSF shall enforce the access control SFP to objects based on subject and object security attributes.",
     "FDP_ACF.1.1-4: Security attribute based access control.", "FDP_ACC.1, FMT_MSA.3"),

    ("FDP", "User Data Protection", "FDP_ETC", "Export from the TOE",
     "FDP_ETC.1", "Export of user data without security attributes",
     "The TSF shall enforce the applicable access control SFP when exporting user data.",
     "FDP_ETC.1.1-2: Export without security attributes.", "FDP_ACC.1"),

    ("FDP", "User Data Protection", "FDP_IFC", "Information Flow Control Policy",
     "FDP_IFC.1", "Subset information flow control",
     "The TSF shall enforce the information flow control SFP on a subset of information flows.",
     "FDP_IFC.1.1: Subset information flow control.", "FDP_IFF.1"),

    ("FDP", "User Data Protection", "FDP_IFF", "Information Flow Control Functions",
     "FDP_IFF.1", "Simple security attributes",
     "The TSF shall enforce the information flow control SFP based on security attributes of subjects and information.",
     "FDP_IFF.1.1-6: Simple security attributes.", "FDP_IFC.1, FMT_MSA.3"),

    ("FDP", "User Data Protection", "FDP_ITC", "Import from outside the TOE",
     "FDP_ITC.1", "Import of user data without security attributes",
     "The TSF shall enforce the applicable access control SFP when importing user data from outside the TOE.",
     "FDP_ITC.1.1-3: Import without security attributes.", "FDP_ACC.1"),

    ("FDP", "User Data Protection", "FDP_RIP", "Residual Information Protection",
     "FDP_RIP.1", "Subset residual information protection",
     "The TSF shall ensure that any previous information content of a resource is made unavailable upon the de-allocation of the resource.",
     "FDP_RIP.1.1: Residual information protection.", None),

    ("FDP", "User Data Protection", "FDP_ROL", "Rollback",
     "FDP_ROL.1", "Basic rollback",
     "The TSF shall enforce rollback of operations on objects covered by the access control SFP.",
     "FDP_ROL.1.1-2: Basic rollback.", "FDP_ACC.1"),

    ("FDP", "User Data Protection", "FDP_SDI", "Stored Data Integrity",
     "FDP_SDI.1", "Stored data integrity monitoring",
     "The TSF shall monitor user data stored in containers controlled by the TSF for integrity errors on all objects.",
     "FDP_SDI.1.1: Stored data integrity monitoring.", None),

    ("FDP", "User Data Protection", "FDP_UCT", "Inter-TSF User Data Confidentiality Transfer Protection",
     "FDP_UCT.1", "Basic data exchange confidentiality",
     "The TSF shall enforce the applicable access control SFP to be able to transmit and receive user data in a manner protected from unauthorised disclosure.",
     "FDP_UCT.1.1: Data exchange confidentiality.", "FDP_ACC.1, FTP_ITC.1"),

    ("FDP", "User Data Protection", "FDP_UIT", "Inter-TSF User Data Integrity Transfer Protection",
     "FDP_UIT.1", "Data exchange integrity",
     "The TSF shall enforce the applicable access control SFP to be able to transmit and receive user data in a manner protected from modification, deletion, insertion, and replay errors.",
     "FDP_UIT.1.1-2: Data exchange integrity.", "FDP_ACC.1, FTP_ITC.1"),

    # ── FIA: Identification and Authentication ───────────
    ("FIA", "Identification and Authentication", "FIA_AFL", "Authentication Failures",
     "FIA_AFL.1", "Authentication failure handling",
     "The TSF shall detect when an administrator configurable positive integer number of unsuccessful authentication attempts occur.",
     "FIA_AFL.1.1-2: Authentication failure handling.", "FIA_UAU.1"),

    ("FIA", "Identification and Authentication", "FIA_ATD", "User Attribute Definition",
     "FIA_ATD.1", "User attribute definition",
     "The TSF shall maintain the following list of security attributes belonging to individual users.",
     "FIA_ATD.1.1: User attribute definition.", None),

    ("FIA", "Identification and Authentication", "FIA_SOS", "Specification of Secrets",
     "FIA_SOS.1", "Verification of secrets",
     "The TSF shall provide a mechanism to verify that secrets meet the requirements of a specified quality metric.",
     "FIA_SOS.1.1: Secret quality verification.", None),

    ("FIA", "Identification and Authentication", "FIA_UAU", "User Authentication",
     "FIA_UAU.1", "Timing of authentication",
     "The TSF shall allow actions on behalf of the user to be performed before the user is authenticated.",
     "FIA_UAU.1.1-2: Authentication timing.", "FIA_UID.1"),

    ("FIA", "Identification and Authentication", "FIA_UAU", "User Authentication",
     "FIA_UAU.2", "User authentication before any action",
     "The TSF shall require each user to be successfully authenticated before allowing any other TSF-mediated actions on behalf of that user.",
     "FIA_UAU.2.1: Authentication before actions.", "FIA_UID.1"),

    ("FIA", "Identification and Authentication", "FIA_UAU", "User Authentication",
     "FIA_UAU.5", "Multiple authentication mechanisms",
     "The TSF shall provide multiple authentication mechanisms to support user authentication.",
     "FIA_UAU.5.1-2: Multiple authentication mechanisms.", "FIA_UID.1"),

    ("FIA", "Identification and Authentication", "FIA_UID", "User Identification",
     "FIA_UID.1", "Timing of identification",
     "The TSF shall allow actions on behalf of the user to be performed before the user is identified.",
     "FIA_UID.1.1-2: Timing of identification.", None),

    ("FIA", "Identification and Authentication", "FIA_UID", "User Identification",
     "FIA_UID.2", "User identification before any action",
     "The TSF shall require each user to be successfully identified before allowing any other TSF-mediated actions on behalf of that user.",
     "FIA_UID.2.1: Identification before actions.", None),

    ("FIA", "Identification and Authentication", "FIA_USB", "User-Subject Binding",
     "FIA_USB.1", "User-subject binding",
     "The TSF shall associate the following user security attributes with subjects acting on behalf of that user.",
     "FIA_USB.1.1-3: User-subject binding.", "FIA_ATD.1"),

    # ── FMT: Security Management ─────────────────────────
    ("FMT", "Security Management", "FMT_MOF", "Management of Functions in TSF",
     "FMT_MOF.1", "Management of security functions behaviour",
     "The TSF shall restrict the ability to determine the behaviour of, disable, enable, modify the behaviour of the functions to authorised roles.",
     "FMT_MOF.1.1: Management of security function behaviour.", "FMT_SMR.1"),

    ("FMT", "Security Management", "FMT_MSA", "Management of Security Attributes",
     "FMT_MSA.1", "Management of security attributes",
     "The TSF shall enforce the applicable access control SFP to restrict the ability to change security attributes to authorised roles.",
     "FMT_MSA.1.1: Management of security attributes.", "FDP_ACC.1, FMT_SMR.1"),

    ("FMT", "Security Management", "FMT_MSA", "Management of Security Attributes",
     "FMT_MSA.3", "Static attribute initialisation",
     "The TSF shall enforce the applicable access control SFP to provide restrictive default values for security attributes.",
     "FMT_MSA.3.1-2: Static attribute initialisation.", "FMT_MSA.1, FMT_SMR.1"),

    ("FMT", "Security Management", "FMT_MTD", "Management of TSF Data",
     "FMT_MTD.1", "Management of TSF data",
     "The TSF shall restrict the ability to change, query, modify, delete TSF data to authorised roles.",
     "FMT_MTD.1.1: Management of TSF data.", "FMT_SMR.1"),

    ("FMT", "Security Management", "FMT_REV", "Revocation",
     "FMT_REV.1", "Revocation",
     "The TSF shall restrict the ability to revoke security attributes associated with subjects, users, objects within the TSC to authorised roles.",
     "FMT_REV.1.1-2: Revocation.", "FMT_SMR.1"),

    ("FMT", "Security Management", "FMT_SAE", "Security Attribute Expiration",
     "FMT_SAE.1", "Time-limited authorisation",
     "The TSF shall restrict the capability to specify an expiration time for security attributes to authorised roles.",
     "FMT_SAE.1.1-2: Time-limited authorisation.", "FMT_SMR.1"),

    ("FMT", "Security Management", "FMT_SMF", "Specification of Management Functions",
     "FMT_SMF.1", "Specification of management functions",
     "The TSF shall be capable of performing the following security management functions.",
     "FMT_SMF.1.1: Security management functions.", None),

    ("FMT", "Security Management", "FMT_SMR", "Security Management Roles",
     "FMT_SMR.1", "Security roles",
     "The TSF shall maintain the roles of authorised users, and shall be able to associate users with roles.",
     "FMT_SMR.1.1-2: Security roles.", "FIA_UID.1"),

    ("FMT", "Security Management", "FMT_SMR", "Security Management Roles",
     "FMT_SMR.2", "Restrictions on security roles",
     "The TSF shall maintain the roles and conditions for roles, and be able to associate users with roles.",
     "FMT_SMR.2.1-3: Restrictions on security roles.", "FIA_UID.1"),

    # ── FPR: Privacy ─────────────────────────────────────
    ("FPR", "Privacy", "FPR_ANO", "Anonymity",
     "FPR_ANO.1", "Anonymity",
     "The TSF shall ensure that users are unable to determine the real user name bound to a subject or operation.",
     "FPR_ANO.1.1: Anonymity protection.", None),

    ("FPR", "Privacy", "FPR_PSE", "Pseudonymity",
     "FPR_PSE.1", "Pseudonymity",
     "The TSF shall ensure that a set of users and/or subjects can use a resource without exposing their identity.",
     "FPR_PSE.1.1-3: Pseudonymity.", None),

    ("FPR", "Privacy", "FPR_UNL", "Unlinkability",
     "FPR_UNL.1", "Unlinkability",
     "The TSF shall ensure that users and/or subjects are unable to determine whether the same user caused specific operations in the system.",
     "FPR_UNL.1.1: Unlinkability.", None),

    # ── FPT: Protection of the TSF ───────────────────────
    ("FPT", "Protection of the TSF", "FPT_FLS", "Fail Secure",
     "FPT_FLS.1", "Failure with preservation of secure state",
     "The TSF shall preserve a secure state when the following types of failures occur.",
     "FPT_FLS.1.1: Failure with preservation of secure state.", None),

    ("FPT", "Protection of the TSF", "FPT_ITC", "Inter-TSF Confidentiality During Transmission",
     "FPT_ITC.1", "Inter-TSF confidentiality during transmission",
     "The TSF shall protect all TSF data transmitted from the TSF to a remote trusted IT product from unauthorised disclosure during transmission.",
     "FPT_ITC.1.1: Confidentiality during transmission.", None),

    ("FPT", "Protection of the TSF", "FPT_ITI", "Inter-TSF Detection of Modification",
     "FPT_ITI.1", "Inter-TSF detection of modification",
     "The TSF shall provide the capability to detect modification of all TSF data during transmission between the TSF and a remote trusted IT product.",
     "FPT_ITI.1.1-2: Detection of modification.", None),

    ("FPT", "Protection of the TSF", "FPT_ITT", "Internal TOE TSF Data Transfer",
     "FPT_ITT.1", "Basic internal TSF data transfer protection",
     "The TSF shall protect TSF data from modification/disclosure when it is transmitted between separate parts of the TOE.",
     "FPT_ITT.1.1: Internal TSF data transfer protection.", None),

    ("FPT", "Protection of the TSF", "FPT_PHP", "TSF Physical Protection",
     "FPT_PHP.1", "Passive detection of physical attack",
     "The TSF shall provide unambiguous detection of physical tampering that might compromise the TSF.",
     "FPT_PHP.1.1-2: Passive detection of physical attack.", None),

    ("FPT", "Protection of the TSF", "FPT_RCV", "Trusted Recovery",
     "FPT_RCV.1", "Manual recovery",
     "The TSF shall only enter a maintenance mode with the involvement of an authorised user.",
     "FPT_RCV.1.1: Manual recovery.", "AGD_OPE.1"),

    ("FPT", "Protection of the TSF", "FPT_RPL", "Replay Detection",
     "FPT_RPL.1", "Replay detection",
     "The TSF shall detect replay for the following entities.",
     "FPT_RPL.1.1-2: Replay detection.", None),

    ("FPT", "Protection of the TSF", "FPT_SSP", "State Synchrony Protocol",
     "FPT_SSP.1", "Simple trusted acknowledgement",
     "The TSF shall acknowledge all data received from a remote trusted IT product.",
     "FPT_SSP.1.1: Simple trusted acknowledgement.", None),

    ("FPT", "Protection of the TSF", "FPT_STM", "Time Stamps",
     "FPT_STM.1", "Reliable time stamps",
     "The TSF shall be able to provide reliable time stamps.",
     "FPT_STM.1.1: Reliable time stamps.", None),

    ("FPT", "Protection of the TSF", "FPT_TDC", "Inter-TSF TSF Data Consistency",
     "FPT_TDC.1", "Basic inter-TSF TSF data consistency",
     "The TSF shall provide the capability to consistently interpret TSF data when shared between the TOE and another trusted IT product.",
     "FPT_TDC.1.1-2: TSF data consistency.", None),

    ("FPT", "Protection of the TSF", "FPT_TRC", "Internal TOE TSF Data Replication Consistency",
     "FPT_TRC.1", "Internal TSF consistency",
     "The TSF shall ensure that TSF data is consistent when replicated between parts of the TOE.",
     "FPT_TRC.1.1-2: Internal TSF consistency.", None),

    ("FPT", "Protection of the TSF", "FPT_TST", "TSF Self Test",
     "FPT_TST.1", "TSF testing",
     "The TSF shall run a suite of self tests during initial start-up to demonstrate the correct operation of the TSF.",
     "FPT_TST.1.1-3: TSF self testing.", None),

    # ── FRU: Resource Utilisation ────────────────────────
    ("FRU", "Resource Utilisation", "FRU_FLT", "Fault Tolerance",
     "FRU_FLT.1", "Degraded fault tolerance",
     "The TSF shall ensure the operation of specified capabilities of the TOE when the following faults occur.",
     "FRU_FLT.1.1: Degraded fault tolerance.", "FPT_FLS.1"),

    ("FRU", "Resource Utilisation", "FRU_PRS", "Priority of Service",
     "FRU_PRS.1", "Limited priority of service",
     "The TSF shall assign a priority to each subject in the TSC and shall ensure that each subject which requests a resource will be provided service.",
     "FRU_PRS.1.1: Limited priority of service.", None),

    ("FRU", "Resource Utilisation", "FRU_RSA", "Resource Allocation",
     "FRU_RSA.1", "Maximum quotas",
     "The TSF shall enforce maximum quotas of the following resources that individual users and/or subjects can use.",
     "FRU_RSA.1.1: Maximum quotas.", None),

    # ── FTA: TOE Access ──────────────────────────────────
    ("FTA", "TOE Access", "FTA_LSA", "Limitation on Scope of Selectable Attributes",
     "FTA_LSA.1", "Limitation on scope of selectable attributes",
     "The TSF shall restrict the scope of the session security attributes that an authorised user can select during session establishment.",
     "FTA_LSA.1.1: Limitation on scope of session attributes.", None),

    ("FTA", "TOE Access", "FTA_MCS", "Limitation on Multiple Concurrent Sessions",
     "FTA_MCS.1", "Basic limitation on multiple concurrent sessions",
     "The TSF shall restrict the maximum number of concurrent sessions that belong to the same user.",
     "FTA_MCS.1.1-2: Limitation on concurrent sessions.", "FIA_UID.1"),

    ("FTA", "TOE Access", "FTA_SSL", "Session Locking and Termination",
     "FTA_SSL.1", "TSF-initiated session locking",
     "The TSF shall lock an interactive session after a period of user inactivity.",
     "FTA_SSL.1.1-2: TSF-initiated session locking.", "FIA_UAU.1"),

    ("FTA", "TOE Access", "FTA_SSL", "Session Locking and Termination",
     "FTA_SSL.3", "TSF-initiated termination",
     "The TSF shall terminate an interactive session after a period of user inactivity.",
     "FTA_SSL.3.1: TSF-initiated session termination.", None),

    ("FTA", "TOE Access", "FTA_TAB", "TOE Access Banners",
     "FTA_TAB.1", "Default TOE access banners",
     "Before establishing a user session, the TSF shall display an advisory warning message regarding unauthorised use of the TOE.",
     "FTA_TAB.1.1: Default access banners.", None),

    ("FTA", "TOE Access", "FTA_TAH", "TOE Access History",
     "FTA_TAH.1", "TOE access history",
     "Upon successful session establishment, the TSF shall display the history of the user's previous sessions.",
     "FTA_TAH.1.1-3: TOE access history.", "FIA_UID.1"),

    ("FTA", "TOE Access", "FTA_TSE", "TOE Session Establishment",
     "FTA_TSE.1", "TOE session establishment",
     "The TSF shall be able to deny session establishment based on specified attributes.",
     "FTA_TSE.1.1: Session establishment control.", None),

    # ── FTP: Trusted Path/Channels ───────────────────────
    ("FTP", "Trusted Path/Channels", "FTP_ITC", "Inter-TSF Trusted Channel",
     "FTP_ITC.1", "Inter-TSF trusted channel",
     "The TSF shall provide a communication channel between itself and another trusted IT product that is logically distinct from other communication channels.",
     "FTP_ITC.1.1-3: Inter-TSF trusted channel.", None),

    ("FTP", "Trusted Path/Channels", "FTP_TRP", "Trusted Path",
     "FTP_TRP.1", "Trusted path",
     "The TSF shall provide a communication path between itself and local/remote users that is logically distinct from other communication paths.",
     "FTP_TRP.1.1-3: Trusted path.", None),
]


async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        # Check if already seeded
        res = await db.exec(select(SFRLibrary).limit(1))
        if res.first():
            print("SFR library already contains data. Checking for missing entries...")

        existing_res = await db.exec(select(SFRLibrary.sfr_component))
        existing = {r for r in existing_res.all()}

        added = 0
        for row in SFR_DATA:
            (sfr_class, sfr_class_name, sfr_family, sfr_family_name,
             sfr_component, sfr_component_name, description, element_text, dependencies) = row

            if sfr_component in existing:
                continue

            item = SFRLibrary(
                sfr_class=sfr_class,
                sfr_class_name=sfr_class_name,
                sfr_family=sfr_family,
                sfr_family_name=sfr_family_name,
                sfr_component=sfr_component,
                sfr_component_name=sfr_component_name,
                description=description,
                element_text=element_text,
                dependencies=dependencies,
                cc_version="3.1R5",
            )
            db.add(item)
            existing.add(sfr_component)
            added += 1

        await db.commit()
    print(f"SFR library import complete. Added {added} entries; total entries: {len(existing)}.")


if __name__ == "__main__":
    asyncio.run(seed())

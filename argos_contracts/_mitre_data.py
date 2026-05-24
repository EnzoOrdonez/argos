"""Curated MITRE ATT&CK technique IDs relevant to ARGOS detection scope.

This is **data**, not code logic. Maintained as a hand-curated subset of
MITRE ATT&CK Enterprise covering the kill chain of ransomware operations
and the techniques that the four detection layers (Sigma, ML, Canary,
LLM Triage) can reasonably identify in this lab.

Refresh policy: re-evaluate quarterly against
https://attack.mitre.org/techniques/enterprise/ — add IDs as new TTPs
become relevant to the demo scenarios or evaluation runs. Removal of an
ID requires confirming no Sigma rule, ML feature, or LLM prompt
references it.

Why hand-curated instead of dynamic STIX bundle load:
    The STIX bundle has ~600 techniques. The signal-to-noise ratio for
    a ransomware-focused EDR/XDR is low — flooding the LLM whitelist
    with unrelated techniques (e.g. cloud privilege escalation, supply
    chain compromise) would not help and would mask hallucinations of
    plausible-but-irrelevant IDs.

    The curated set below is the explicit allowlist of "techniques we
    care about". Any LLM output outside this set is either a true
    hallucination or a signal that we should expand the set deliberately
    (with a code review).
"""

# Techniques are grouped by MITRE tactic for maintainability.
# Each ID maps to a short label used only for code review — runtime
# validation only checks membership, not the label.

_TECHNIQUES_BY_TACTIC: dict[str, dict[str, str]] = {
    "initial_access": {
        "T1078": "Valid Accounts",
        "T1190": "Exploit Public-Facing Application",
        "T1566": "Phishing",
    },
    "execution": {
        "T1059": "Command and Scripting Interpreter",
        "T1059.001": "PowerShell",
        "T1059.003": "Windows Command Shell",
        "T1059.004": "Unix Shell",
        "T1204": "User Execution",
        "T1569": "System Services",
    },
    "persistence": {
        "T1053": "Scheduled Task/Job",
        "T1543": "Create or Modify System Process",
        "T1547": "Boot or Logon Autostart Execution",
    },
    "privilege_escalation": {
        "T1068": "Exploitation for Privilege Escalation",
        "T1134": "Access Token Manipulation",
    },
    "defense_evasion": {
        "T1027": "Obfuscated Files or Information",
        "T1070": "Indicator Removal",
        "T1070.001": "Clear Windows Event Logs",
        "T1070.004": "File Deletion",
        "T1112": "Modify Registry",
        "T1140": "Deobfuscate/Decode Files or Information",
        "T1562": "Impair Defenses",
        "T1562.001": "Disable or Modify Tools",
        "T1562.004": "Disable or Modify System Firewall",
    },
    "credential_access": {
        "T1003": "OS Credential Dumping",
        "T1110": "Brute Force",
        "T1555": "Credentials from Password Stores",
    },
    "discovery": {
        "T1018": "Remote System Discovery",
        "T1057": "Process Discovery",
        "T1082": "System Information Discovery",
        "T1083": "File and Directory Discovery",
        "T1087": "Account Discovery",
        "T1135": "Network Share Discovery",
    },
    "lateral_movement": {
        "T1021": "Remote Services",
        "T1021.001": "Remote Desktop Protocol",
        "T1021.002": "SMB/Windows Admin Shares",
        "T1021.004": "SSH",
    },
    "collection": {
        "T1005": "Data from Local System",
        "T1039": "Data from Network Shared Drive",
        "T1560": "Archive Collected Data",
    },
    "command_and_control": {
        "T1071": "Application Layer Protocol",
        "T1071.001": "Web Protocols",
        "T1095": "Non-Application Layer Protocol",
        "T1573": "Encrypted Channel",
    },
    "exfiltration": {
        "T1041": "Exfiltration Over C2 Channel",
        "T1048": "Exfiltration Over Alternative Protocol",
    },
    "impact": {
        "T1485": "Data Destruction",
        "T1486": "Data Encrypted for Impact",
        "T1489": "Service Stop",
        "T1490": "Inhibit System Recovery",
        "T1491": "Defacement",
        "T1496": "Resource Hijacking",
        "T1529": "System Shutdown/Reboot",
        "T1657": "Financial Theft",
    },
}


def _build_whitelist() -> frozenset[str]:
    """Flatten the by-tactic dict into a frozen set for O(1) membership tests."""
    return frozenset(
        technique_id
        for tactic_dict in _TECHNIQUES_BY_TACTIC.values()
        for technique_id in tactic_dict
    )


# Module-level constant consumed by argos_contracts.triage.TriageResponse
# validation. Frozen at import time; mutating it requires a code change
# + new release of argos_contracts.
MITRE_WHITELIST: frozenset[str] = _build_whitelist()


__all__ = ["MITRE_WHITELIST"]

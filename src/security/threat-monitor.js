#!/usr/bin/env node
// threat-monitor.js — OWASP, NVD, and GitHub advisory checker

const NVD_BASE = 'https://services.nvd.nist.gov/rest/json/cves/2.0';
const GITHUB_ADVISORIES = 'https://api.github.com/advisories';

async function checkNVD() {
  const now = new Date();
  const past = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  // NVD requires format: 2021-08-04T13:00:00.000 (no Z, no UTC suffix)
  const fmt = d => d.toISOString().replace('Z', '').replace(/\.\d{3}$/, '.000');
  const url = `${NVD_BASE}?pubStartDate=${fmt(past)}&pubEndDate=${fmt(now)}&keywordSearch=Node.js+Python&resultsPerPage=5`;

  try {
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Korvin-Threat-Monitor/1.0',
        'Accept': 'application/json',
      }
    });
    if (!res.ok) throw new Error(`NVD API error: ${res.status} — ${await res.text()}`);
    const data = await res.json();
    return (data.vulnerabilities || []).map(v => ({
      id: v.cve.id,
      description: v.cve.descriptions?.[0]?.value?.substring(0, 200),
      severity: v.cve.metrics?.cvssMetricV31?.[0]?.cvssData?.baseSeverity ||
                v.cve.metrics?.cvssMetricV30?.[0]?.cvssData?.baseSeverity || 'UNKNOWN',
    }));
  } catch (err) {
    console.error('NVD check failed:', err.message);
    return [];
  }
}

async function checkGitHubAdvisories() {
  const url = `${GITHUB_ADVISORIES}?severity=high&type=reviewed&per_page=5`;
  try {
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Korvin-Threat-Monitor/1.0',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    });
    if (!res.ok) throw new Error(`GitHub API error: ${res.status} — ${await res.text()}`);
    const advisories = await res.json();
    return advisories.map(a => ({
      id: a.ghsa_id,
      summary: a.summary?.substring(0, 200),
      severity: a.severity,
      package: a.vulnerabilities?.[0]?.package?.name || 'unknown',
      ecosystem: a.vulnerabilities?.[0]?.package?.ecosystem || 'unknown',
    }));
  } catch (err) {
    console.error('GitHub advisories check failed:', err.message);
    return [];
  }
}

function checkOWASP() {
  return [
    { id: 'A01:2021', title: 'Broken Access Control' },
    { id: 'A02:2021', title: 'Cryptographic Failures' },
    { id: 'A03:2021', title: 'Injection' },
    { id: 'A04:2021', title: 'Insecure Design' },
    { id: 'A05:2021', title: 'Security Misconfiguration' },
    { id: 'A06:2021', title: 'Vulnerable and Outdated Components' },
    { id: 'A07:2021', title: 'Identification and Authentication Failures' },
    { id: 'A08:2021', title: 'Software and Data Integrity Failures' },
    { id: 'A09:2021', title: 'Security Logging and Monitoring Failures' },
    { id: 'A10:2021', title: 'Server-Side Request Forgery (SSRF)' },
  ];
}

async function runMonitor() {
  console.log('Korvin Threat Monitor — running checks...\n');

  console.log('=== NVD CVEs (last 7 days, Node.js/Python) ===');
  const cves = await checkNVD();
  cves.forEach(c => console.log(`[${c.severity}] ${c.id}: ${c.description}`));
  if (cves.length === 0) console.log('No recent CVEs found.');

  console.log('\n=== GitHub Security Advisories (high+) ===');
  const advisories = await checkGitHubAdvisories();
  advisories.forEach(a => console.log(`[${a.severity}] ${a.id} (${a.ecosystem}/${a.package}): ${a.summary}`));
  if (advisories.length === 0) console.log('No high/critical advisories found.');

  console.log('\n=== OWASP Top 10 (2021) ===');
  checkOWASP().forEach(o => console.log(`${o.id}: ${o.title}`));

  console.log('\nMonitor run complete.');
}

module.exports = { runMonitor };

if (require.main === module) {
  runMonitor().catch(console.error);
}

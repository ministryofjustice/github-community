export const REQUEST_VERSION = 1;
export const REQUEST_LIMIT = 100;

export function requestDetails(team, project) {
  if (typeof team !== "string" || !team.trim() || team.trim().length > 80) {
    throw new Error("Enter a team name of up to 80 characters.");
  }
  if (typeof project !== "string" || project.length > 300
    || !/^https:\/\/github\.com\/orgs\/[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\/projects\/[1-9]\d*\/?$/.test(project.trim())) {
    throw new Error("Enter a GitHub organisation project link.");
  }
  const url = new URL(project.trim());
  return { team: team.trim(), project: `${url.origin}${url.pathname.replace(/\/$/, "").toLowerCase()}` };
}

export function requestKey(request) {
  return `${request.team.toLowerCase()}\n${request.project}`;
}

export function parseRequests(raw) {
  if (raw === null) return [];
  if (raw.length > 100000) throw new Error("Stored requests exceed the browser storage limit.");
  const data = JSON.parse(raw);
  if (!data || data.version !== REQUEST_VERSION || Object.keys(data).sort().join() !== "requests,version"
    || !Array.isArray(data.requests) || data.requests.length > REQUEST_LIMIT) {
    throw new Error("Stored requests have an unsupported format.");
  }
  const ids = new Set(), keys = new Set();
  return data.requests.map(request => {
    if (!request || Object.keys(request).sort().join() !== "id,project,team"
      || typeof request.id !== "string" || !/^[a-f0-9-]{36}$/.test(request.id)) {
      throw new Error("A stored request is invalid.");
    }
    const details = requestDetails(request.team, request.project);
    const key = requestKey(details);
    if (ids.has(request.id) || keys.has(key)) throw new Error("Stored requests contain duplicates.");
    ids.add(request.id); keys.add(key);
    return { id: request.id, ...details };
  });
}

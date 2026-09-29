(function (root) {
  function parseDate(value) {
    if (value instanceof Date) return new Date(value.getTime());
    return new Date(value);
  }

  function userTimeZone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
    } catch {
      return undefined;
    }
  }

  function dateParts(date, timeZone) {
    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23'
    });
    return Object.fromEntries(formatter.formatToParts(date)
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, part.value]));
  }

  function timeZoneOffset(date, timeZone) {
    const parts = dateParts(date, timeZone);
    const projectedUtc = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour), Number(parts.minute), Number(parts.second)
    );
    const offsetMinutes = Math.round((projectedUtc - date.getTime()) / 60000);
    const sign = offsetMinutes >= 0 ? '+' : '-';
    const absolute = Math.abs(offsetMinutes);
    return `UTC${sign}${String(Math.floor(absolute / 60)).padStart(2, '0')}:${String(absolute % 60).padStart(2, '0')}`;
  }

  function formatLocalDateTime(value = new Date(), options = {}) {
    const date = parseDate(value);
    if (Number.isNaN(date.getTime())) return '无效时间';
    const timeZone = options.timeZone || userTimeZone();
    const parts = dateParts(date, timeZone);
    const display = `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
    const zoneLabel = timeZone || timeZoneOffset(date, timeZone);
    return `${display}（${zoneLabel}，${timeZoneOffset(date, timeZone)}）`;
  }

  function isTimestamp(value) {
    if (value instanceof Date || typeof value === 'number') return true;
    return /^\d{4}-\d{2}-\d{2}T/.test(String(value || '').trim());
  }

  const api = { formatLocalDateTime, isTimestamp, userTimeZone };
  root.WandaoTime = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);

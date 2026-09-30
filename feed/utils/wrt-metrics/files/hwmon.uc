// Temperatures of the hwmon devices, named as node_exporter names them
// (r4s-services D8). On every board, rockchip-thermal registers the SoC's thermal
// zones there; a system without sensors has no series, which is no failure.
const root = "/sys/class/hwmon/";
const chips = fs.lsdir(root);

if (chips == null)
	return false;

const m_chip = gauge("node_hwmon_chip_names");
const m_temp = gauge("node_hwmon_temp_celsius");
const m_crit = gauge("node_hwmon_temp_crit_celsius");
const m_max = gauge("node_hwmon_temp_max_celsius");

for (let chip in chips) {
	const dir = root + chip + "/";
	m_chip({ chip, chip_name: oneline(dir + "name") }, 1);

	for (let input in fs.lsdir(dir, "temp*_input")) {
		const sensor = substr(input, 0, -6);
		m_temp({ chip, sensor }, int(oneline(dir + input)) / 1000.0);

		const crit = oneline(dir + sensor + "_crit");
		if (crit != null)
			m_crit({ chip, sensor }, int(crit) / 1000.0);

		const max = oneline(dir + sensor + "_max");
		if (max != null)
			m_max({ chip, sensor }, int(max) / 1000.0);
	}
}

export interface PortInfo {
  port: number;
  pid: number;
  process_name: string;
  protocol: string;
  local_address: string;
  state?: string;
}

export interface ScanResult {
  timestamp: string;
  ports: PortInfo[];
}

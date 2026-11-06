-- Phase 22r: at frame VR_DUMP_FRAME (default 300) write the ranking tables' battery RAM (0x40c900-0x40e700, VR_RANKING_DUMP) and exit
local mem = manager.machine.devices[":maincpu"].spaces["program"]
local at = tonumber(os.getenv("VR_DUMP_FRAME") or "300")
local frame = 0
emu.register_frame_done(function()
  frame = frame + 1
  if frame == at then
    local f = assert(io.open(os.getenv("VR_RANKING_DUMP"), "wb")); f:write(mem:read_range(0x40c900, 0x40ffff, 8)); f:close()
    manager.machine:exit()
  end
end)

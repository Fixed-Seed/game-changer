// The handful of GTA V natives the passthrough needs, called by hash (names from the community GTA V native DB;
// ScriptHookV translates the original PC hashes for the running build).
#pragma once
#include <types.h>
#include <nativeCaller.h>

namespace natives
{
	inline Vector3 GetFinalRenderedCamCoord() { return invoke<Vector3>(0xA200EB1EE790F448); }
	inline Vector3 GetFinalRenderedCamRot(int order) { return invoke<Vector3>(0x5B4E4C817FCC2DFB, order); }
	inline float GetFinalRenderedCamFov() { return invoke<float>(0x80EC114669DAEFF4); }
	inline float GetFinalRenderedCamNearClip() { return invoke<float>(0xD0082607100D7193); }
	inline float GetFinalRenderedCamFarClip() { return invoke<float>(0xDFC8CBC606FDB0FC); }
	inline int GetFollowPedCamViewMode() { return invoke<int>(0x8D4D46230B2C353A); }
	inline int GetFollowVehicleCamViewMode() { return invoke<int>(0xA4FF579AC0E3AAAE); }
	inline BOOL IsScreenFadedOut() { return invoke<BOOL>(0xB16FCE9DDC7BA182); }
	inline BOOL IsCutsceneActive() { return invoke<BOOL>(0x991251AFC3981F84); }
	inline BOOL IsPlayerSwitchInProgress() { return invoke<BOOL>(0xD9D2CFFF49FAB35F); }

	inline void AddExplosion(float x, float y, float z, int type, float damage, BOOL audible, BOOL invisible, float shake, BOOL noDamage)
	{
		invoke<Void>(0xE3AD2BDBAEE269AC, x, y, z, type, damage, audible, invisible, shake, noDamage);
	}
	inline BOOL GetGroundZFor3dCoord(float x, float y, float z, float *groundZ, BOOL ignoreWater, BOOL p5)
	{
		return invoke<BOOL>(0xC906A7DAB05C8D2B, x, y, z, groundZ, ignoreWater, p5);
	}

	inline void DisableControlAction(int group, int control, BOOL disable) { invoke<Void>(0xFE99B66D079CF6BC, group, control, disable); }
	inline BOOL IsDisabledControlJustPressed(int group, int control) { return invoke<BOOL>(0x91AEF906BCA88877, group, control); }
	inline BOOL IsDisabledControlJustReleased(int group, int control) { return invoke<BOOL>(0x305C8DCD79DA8B0F, group, control); }

	inline void HideHudAndRadarThisFrame() { invoke<Void>(0x719FF505F097FD20); }
	inline void TheFeedHideThisFrame() { invoke<Void>(0x25F87B30C382FCA7); }
	inline void HideHelpTextThisFrame() { invoke<Void>(0xD46923FC481CA285); }
	inline BOOL IsPauseMenuActive() { return invoke<BOOL>(0xB0034A223497FFCB); }
	inline void GetActualScreenResolution(int *x, int *y) { invoke<Void>(0x873C9F3104101DD3, x, y); }

	inline Ped PlayerPedId() { return invoke<Ped>(0xD80958FC74E988A6); }
	inline Vector3 GetEntityCoords(Entity e, BOOL alive) { return invoke<Vector3>(0x3FEF770D40960D5A, e, alive); }
	inline float GetEntityHeading(Entity e) { return invoke<float>(0xE83D4F9BA2A38914, e); }
	inline float GetEntityHeightAboveGround(Entity e) { return invoke<float>(0x1DD55701034110E5, e); }
	inline void SetEntityVisible(Entity e, BOOL visible, BOOL p2) { invoke<Void>(0xEA1C610A04DB6BBB, e, visible, p2); }
	inline void SetEntityLocallyInvisible(Entity e) { invoke<Void>(0xE135A9FF3F5D05D8, e); }
	inline BOOL IsPedInAnyVehicle(Ped p, BOOL atGetIn) { return invoke<BOOL>(0x997ABD671D25CA0B, p, atGetIn); }
	inline Vehicle GetVehiclePedIsIn(Ped p, BOOL includeEntering) { return invoke<Vehicle>(0x9A9112A0FE9A4713, p, includeEntering); }
	inline void SetCurrentPedWeapon(Ped p, Hash weapon, BOOL forceInHand) { invoke<Void>(0xADF692B254977C0C, p, weapon, forceInHand); }
	inline void GiveWeaponToPed(Ped p, Hash weapon, int ammo, BOOL hidden, BOOL forceInHand) { invoke<Void>(0xBF0FD6E56C964FCB, p, weapon, ammo, hidden, forceInHand); }
	inline Entity GetCurrentPedWeaponEntityIndex(Ped p) { return invoke<Entity>(0x3B390A939AF0B5FC, p, 0); }
	inline void SetPedInfiniteAmmoClip(Ped p, BOOL on) { invoke<Void>(0x183DADC6AA953186, p, on); }
	inline void ShowHudComponentThisFrame(int id) { invoke<Void>(0x0B4DF1FA60C0E664, id); }
	inline void SetPedCurrentWeaponVisible(Ped p, BOOL visible) { invoke<Void>(0x0725A4CCFDED9A70, p, visible, TRUE, TRUE, TRUE); }
	inline BOOL IsPlayerFreeAiming(Player p) { return invoke<BOOL>(0x2E397FD2ECD37C87, p); }
	inline Vector3 GetGameplayCamCoord() { return invoke<Vector3>(0x14D6F5678D8F1B37); }
	inline float GetGameplayCamFov() { return invoke<float>(0x65019750A0324133); }
	inline void RequestWeaponAsset(Hash w) { invoke<Void>(0x5443438F033E29C3, w, 31, 0); }
	inline BOOL HasWeaponAssetLoaded(Hash w) { return invoke<BOOL>(0x36E353271F0E90EE, w); }
	inline Object CreateWeaponObject(Hash w, float x, float y, float z) { return invoke<Object>(0x9541D3CF0D398F36, w, 0, x, y, z, TRUE, 1.0f, 0, 0, 0); }
	inline int StartShapeTestLosProbe(float x1, float y1, float z1, float x2, float y2, float z2, int flags, Entity ignore)
	{
		return invoke<int>(0x377906D8A31E5586, x1, y1, z1, x2, y2, z2, flags, ignore, 7);
	}
	inline int GetShapeTestResult(int handle, BOOL *hit, Vector3 *end, Vector3 *normal, Entity *entity)
	{
		return invoke<int>(0x3D87450E15D98694, handle, hit, end, normal, entity);
	}
	inline BOOL GetScreenCoordFromWorldCoord(float x, float y, float z, float *sx, float *sy) { return invoke<BOOL>(0x34E82F05DF2974F5, x, y, z, sx, sy); }
	inline void DrawRect(float x, float y, float w, float h, int r, int g, int b, int a) { invoke<Void>(0x3A618A217E5154F0, x, y, w, h, r, g, b, a, FALSE); }

	inline int GetFrameCount() { return invoke<int>(0xFC8202EFC642E6F2); }
	inline int GetGameTimer() { return invoke<int>(0x9CD27B0045628463); }

	// Director (scripted shots) and keeping the invisible GTA player alive through Minecraft's explosions.
	inline Player PlayerId() { return invoke<Player>(0x4F8644AF03D0E0D6); }
	inline void SetEntityCoordsNoOffset(Entity e, float x, float y, float z) { invoke<Void>(0x239A3351AC1DA385, e, x, y, z, FALSE, FALSE, FALSE); }
	inline void SetEntityHeading(Entity e, float h) { invoke<Void>(0x8E2530AA8ADA980E, e, h); }
	inline void TaskGoStraightToCoord(Ped p, float x, float y, float z, float speed, int timeout, float heading, float slide)
	{
		invoke<Void>(0xD76B57B44F1E6F8B, p, x, y, z, speed, timeout, heading, slide);
	}
	inline void ClearPedTasks(Ped p) { invoke<Void>(0xE1EF3C1216AFF2CD, p); }
	inline void SetFollowPedCamViewMode(int mode) { invoke<Void>(0x5A4F9EDF1673F704, mode); }
	inline void SetGameplayCamRelativePitch(float angle, float scale) { invoke<Void>(0x6D0858B8EDFD2B7D, angle, scale); }
	inline void SetGameplayCamRelativeHeading(float heading) { invoke<Void>(0xB4EC2312F4E5B1F1, heading); }
	inline void SetClockTime(int h, int m, int s) { invoke<Void>(0x47C3B5848C3E45D8, h, m, s); }
	inline void PauseClock(BOOL toggle) { invoke<Void>(0x4055E40BD2DBEC1D, toggle); }
	inline void SetWeatherTypeNowPersist(const char *w) { invoke<Void>(0xED712CA327900C8A, w); }
	inline void SetOverrideWeather(const char *w) { invoke<Void>(0xA43D5C6FE51ADBEF, w); }
	inline void SetEntityInvincible(Entity e, BOOL t) { invoke<Void>(0x3882114BDE571AD4, e, t, TRUE); }
	inline void SetPlayerInvincible(Player p, BOOL t) { invoke<Void>(0x239528EACDC3E7DE, p, t); }
	inline void SetEntityProofs(Entity e, BOOL bullet, BOOL fire, BOOL explosion, BOOL collision, BOOL melee)
	{
		invoke<Void>(0xFAEE099C6F890BB8, e, bullet, fire, explosion, collision, melee, TRUE, TRUE, FALSE);
	}
	inline void SetPedCanRagdoll(Ped p, BOOL t) { invoke<Void>(0xB128377056A54E2A, p, t); }
	inline void SetMaxWantedLevel(int level) { invoke<Void>(0xAA5F02DB48D704B9, level); }
	inline void ClearPlayerWantedLevel(Player p) { invoke<Void>(0xB302540597885499, p); }
	inline void SetPoliceIgnorePlayer(Player p, BOOL t) { invoke<Void>(0x32C62AA929C2DA6A, p, t); }
	inline void SetDispatchCopsForPlayer(Player p, BOOL t) { invoke<Void>(0xDB172424876553F4, p, t); }
	inline void SetPlayerWantedLevel(Player p, int level) { invoke<Void>(0x39FF19C64EF7DA5B, p, level, FALSE); }
	inline void SetPlayerWantedLevelNow(Player p) { invoke<Void>(0xE0A7D1E497FFCD6F, p, FALSE); }
	inline int GetPlayerWantedLevel(Player p) { return invoke<int>(0xE28E54788CE8F12D, p); }
	inline int GetEntityType(Entity e) { return invoke<int>(0x8ACD366038D14505, e); }
	inline void ShootSingleBulletBetweenCoords(float x1, float y1, float z1, float x2, float y2, float z2, int damage, Hash weapon, Ped owner)
	{
		invoke<Void>(0x867654CBC7606F2C, x1, y1, z1, x2, y2, z2, damage, TRUE, weapon, owner, TRUE, TRUE, -1.0f);
	}
	inline void SetPedToRagdoll(Ped p, int ms) { invoke<Void>(0xAE99FB955581844A, p, ms, ms, 0, FALSE, FALSE, FALSE); }
	inline void ApplyDamageToPed(Ped p, int damage) { invoke<Void>(0x697157CED63F18D4, p, damage, FALSE, 0, 0); }
	inline void ApplyForceToEntity(Entity e, float x, float y, float z)
	{
		invoke<Void>(0xC5F68BE9613E2D18, e, 1, x, y, z, 0.0f, 0.0f, 0.0f, 0, FALSE, TRUE, TRUE, FALSE, TRUE);
	}
	inline BOOL IsPedDeadOrDying(Ped p) { return invoke<BOOL>(0x3317DEDB88C95038, p, TRUE); }
	// Mobs vs police (hashes and argument counts checked against the community native DB for 3889).
	inline BOOL AddRelationshipGroup(const char *name, Hash *group) { return invoke<BOOL>(0xF372BC22FCB88606, name, group); }
	inline void SetRelationshipBetweenGroups(int rel, Hash g1, Hash g2) { invoke<Void>(0xBF25EB89375A37AD, rel, g1, g2); }
	inline void SetPedRelationshipGroupHash(Ped p, Hash group) { invoke<Void>(0xC80A74AC829DDD92, p, group); }
	inline void SetBlockingOfNonTemporaryEvents(Ped p, BOOL t) { invoke<Void>(0x9F8AA94D6D97DBF4, p, t); }
	inline int GetEntityHealth(Entity e) { return invoke<int>(0xEEF059FAD016D209, e); }
	inline void SetEntityHealth(Entity e, int health) { invoke<Void>(0x6B76DC1F3AE6E6A3, e, health, 0, 0); }
	inline void SetPedMaxHealth(Ped p, int v) { invoke<Void>(0xF5F6378C4F3419D3, p, v); }
	inline int GetPedType(Ped p) { return invoke<int>(0xFF059E1E4C01E63C, p); }
	inline void SetPedAccuracy(Ped p, int accuracy) { invoke<Void>(0x7AEFB85C1D49DEB6, p, accuracy); }
	inline void SetPedCombatAbility(Ped p, int level) { invoke<Void>(0xC7622C0D36B2FDA8, p, level); }
	inline void SetPedCombatRange(Ped p, int range) { invoke<Void>(0x3C606747B23E497B, p, range); }
	inline void SetPedCombatMovement(Ped p, int movement) { invoke<Void>(0x4D9CA1009AFBD057, p, movement); }
	inline void SetPedConfigFlag(Ped p, int flag, BOOL v) { invoke<Void>(0x1913FE4CBF41C463, p, flag, v); }
	inline void SetPedArmour(Ped p, int amount) { invoke<Void>(0xCEA04D83135264CC, p, amount); }
	inline void DeletePed(Ped *p) { invoke<Void>(0x9614299DCB53E54B, p); }
	inline void SetPedSeeingRange(Ped p, float r) { invoke<Void>(0xF29CF591C4BF6CEE, p, r); }
	inline void SetVehicleSiren(Vehicle v, BOOL on) { invoke<Void>(0xF4924635A19EB37D, v, on); }
	inline void SetPedSuffersCriticalHits(Ped p, BOOL t) { invoke<Void>(0xEBD76F2359F190AC, p, t); }
	inline void SetPedDiesWhenInjured(Ped p, BOOL t) { invoke<Void>(0x5BA7919BED300023, p, t); }
	inline void InvalidateIdleCam() { invoke<Void>(0xF4F2C0D4EE209E20); }
	inline void InvalidateCinematicVehicleIdleMode() { invoke<Void>(0x9E4CFFF989258472); }
	// The Nether opening (checked against the community native DB for 3889)
	inline void SetTimecycleModifier(const char *name) { invoke<Void>(0x2C933ABF17A1DF41, name); }
	inline void SetTimecycleModifierStrength(float s) { invoke<Void>(0x82E7FFCD5B2326B3, s); }
	inline void SetTransitionTimecycleModifier(const char *name, float seconds) { invoke<Void>(0x3BCF567485E1971C, name, seconds); }
	inline void ClearTimecycleModifier() { invoke<Void>(0x0F07E7745A236711); }
	inline void AnimpostfxPlay(const char *name, int ms, BOOL looped) { invoke<Void>(0x2206BF9A37B7F724, name, ms, looped); }
	inline void AnimpostfxStop(const char *name) { invoke<Void>(0x068E835A1D0DC0E3, name); }
	inline void ShakeGameplayCam(const char *name, float intensity) { invoke<Void>(0xFD55E49555E017CF, name, intensity); }
	inline void SetWeatherTypeOvertimePersist(const char *w, float seconds) { invoke<Void>(0xFB5045B7C42B75BF, w, seconds); }
	inline int StartEntityFire(Entity e) { return invoke<int>(0xF6A9D9708F6F23DF, e); }
	inline BOOL IsEntityOnFire(Entity e) { return invoke<BOOL>(0x28D3FED7190D3A0B, e); }
	inline int StartScriptFire(float x, float y, float z, int children, BOOL gas) { return invoke<int>(0x6B83617E04503888, x, y, z, children, gas); }
	inline void DoScreenFadeOut(int ms) { invoke<Void>(0x891B5B39AC6302AF, ms); }
	inline void StopGameplayCamShaking(BOOL now) { invoke<Void>(0x0EF93E9F3D08C178, now); }
	inline BOOL IsGameplayCamShaking() { return invoke<BOOL>(0x016C090630DF1F89); }
	inline BOOL IsCinematicCamShaking() { return invoke<BOOL>(0xBBC08F6B4CB8FF0A); }
	inline void StopCinematicCamShaking(BOOL now) { invoke<Void>(0x2238E588E588A6D7, now); }
	inline BOOL IsExplosionInSphere(int type, float x, float y, float z, float radius) { return invoke<BOOL>(0xAB0F816885B0E483, type, x, y, z, radius); }
	inline void SetGameplayCamMotionBlurScalingThisUpdate(float s) { invoke<Void>(0x487A82C650EB7799, s); }
	inline void SetGameplayCamMaxMotionBlurStrengthThisUpdate(float s) { invoke<Void>(0x0225778816FDC28C, s); }
	inline void ClearOverrideWeather() { invoke<Void>(0x338D2E3477711050); }
	inline Hash GetPedRelationshipGroupHash(Ped p) { return invoke<Hash>(0x7DBDD04862D95F04, p); }
	inline void DrawLightWithRange(float x, float y, float z, int r, int g, int b, float range, float intensity)
	{
		invoke<Void>(0xF2A1B2771A01DBD4, x, y, z, r, g, b, range, intensity);
	}
	inline Ped CreatePedInsideVehicle(Vehicle v, Hash model, int seat) { return invoke<Ped>(0x7DD959874C1FD534, v, 26, model, seat, FALSE, TRUE); }
	inline void TaskCombatPed(Ped p, Ped target) { invoke<Void>(0xF166E48407BAC484, p, target, 0, 16); }
	inline void SetPedCombatAttributes(Ped p, int attr, BOOL on) { invoke<Void>(0x9F7794730795E019, p, attr, on); }
	inline void SetPedFleeAttributes(Ped p, int attr, BOOL on) { invoke<Void>(0x70A2D1137C8ED7C9, p, attr, on); }
	inline void SetPedKeepTask(Ped p, BOOL on) { invoke<Void>(0x971D38760FBC02EF, p, on); }
	inline void SetHeliBladesFullSpeed(Vehicle v) { invoke<Void>(0xA178472EBB8AE60D, v); }
	inline void SetVehicleEngineOn(Vehicle v, BOOL on) { invoke<Void>(0x2497C4717C8B881E, v, on, TRUE, FALSE); }
	inline BOOL GetClosestVehicleNodeWithHeading(float x, float y, float z, Vector3 *out, float *heading)
	{
		return invoke<BOOL>(0xFF071FB798B803B0, x, y, z, out, heading, 1, 3.0f, 0);
	}
	inline void DeleteEntity(Entity *e) { invoke<Void>(0xAE3CBE5BF394C9C9, e); }
	inline void SetEntityAsMissionEntity(Entity e) { invoke<Void>(0xAD738C3085FE7E11, e, TRUE, TRUE); }
	inline Hash GetHashKey(const char *s) { return invoke<Hash>(0xD24D37CC275948CC, s); }
	inline void RequestModel(Hash m) { invoke<Void>(0x963D27A58DF860AC, m); }
	inline BOOL HasModelLoaded(Hash m) { return invoke<BOOL>(0x98A4EB5D89A0C952, m); }
	inline void SetModelAsNoLongerNeeded(Hash m) { invoke<Void>(0xE532F5D78798DAAB, m); }
	inline Ped CreatePed(int type, Hash model, float x, float y, float z, float h) { return invoke<Ped>(0xD49F9B0955C367DE, type, model, x, y, z, h, FALSE, TRUE); }
	inline Vehicle CreateVehicle(Hash model, float x, float y, float z, float h) { return invoke<Vehicle>(0xAF35D0D2583051B0, model, x, y, z, h, FALSE, TRUE, FALSE); }
	inline BOOL SetVehicleOnGroundProperly(Vehicle v) { return invoke<BOOL>(0x49733E92263139D1, v, 5.0f); }
	inline void TaskStartScenarioInPlace(Ped p, const char *scenario) { invoke<Void>(0x142A02425FF02BD9, p, scenario, 0, TRUE); }
	inline void TaskWanderStandard(Ped p) { invoke<Void>(0xBB9CE077274F6A1B, p, 10.0f, 10); }
	inline void TaskSmartFleeCoord(Ped p, float x, float y, float z) { invoke<Void>(0x94587F17E9C365D5, p, x, y, z, 100.0f, -1, FALSE, FALSE); }
	inline BOOL NewLoadSceneStartSphere(float x, float y, float z, float r) { return invoke<BOOL>(0xACCFB4ACF53551B0, x, y, z, r, 0); }
	inline BOOL IsNewLoadSceneLoaded() { return invoke<BOOL>(0x01B8247A7A8B9AD1); }
	inline void NewLoadSceneStop() { invoke<Void>(0xC197616D221FF4A4); }
	inline void RequestCollisionAtCoord(float x, float y, float z) { invoke<Void>(0x07503F7948F491A7, x, y, z); }
	inline int GetInteriorFromEntity(Entity e) { return invoke<int>(0x2107BA504071A6BB, e); }
	inline void SetPedDensityMultiplierThisFrame(float m) { invoke<Void>(0x95E3D6257B166CF2, m); }
	inline void DoScreenFadeIn(int ms) { invoke<Void>(0xD4E8E24955024033, ms); }

	// Props standing in for Minecraft blocks (collision, shadows).
	inline Object CreateObjectNoOffset(Hash m, float x, float y, float z) { return invoke<Object>(0x9A294B2138ABB884, m, x, y, z, FALSE, TRUE, FALSE, 0); }
	inline void DeleteObject(Object *o) { invoke<Void>(0x539E0AE3E6634B9F, o); }
	inline BOOL DoesEntityExist(Entity e) { return invoke<BOOL>(0x7239B21A38F536BA, e); }
	inline void FreezeEntityPosition(Entity e, BOOL t) { invoke<Void>(0x428CA6DBD1094446, e, t); }
	inline void SetEntityCollision(Entity e, BOOL t, BOOL keepPhysics) { invoke<Void>(0x1A9205C1B9EE827F, e, t, keepPhysics); }
	inline void SetEntityRotation(Entity e, float p, float r, float y) { invoke<Void>(0x8524A8B0171D5E07, e, p, r, y, 2, TRUE); }
	inline void SetEntityCanBeDamaged(Entity e, BOOL t) { invoke<Void>(0x1760FFA8AB074D66, e, t); }
	inline void SetDisableFragDamage(Object o, BOOL t) { invoke<Void>(0x01BA3AED21C16CFB, o, t); }
	inline void SetEntityLodDist(Entity e, int d) { invoke<Void>(0x5927F96A78577363, e, d); }
	inline BOOL IsModelValid(Hash m) { return invoke<BOOL>(0xC0296A2EDF545E92, m); }
	inline void GetModelDimensions(Hash m, Vector3 *mn, Vector3 *mx) { invoke<Void>(0x03E8D3D5F549087A, m, mn, mx); }
	inline void RequestAnimDict(const char *d) { invoke<Void>(0xD3BD40951412FEF6, d); }
	inline BOOL HasAnimDictLoaded(const char *d) { return invoke<BOOL>(0xD031A9162D01088C, d); }
	inline void TaskPlayAnimLoop(Ped p, const char *d, const char *a)
	{
		invoke<Void>(0xEA47FE3719165B94, p, d, a, 8.0f, -8.0f, -1, 1, 0.0f, FALSE, FALSE, FALSE);
	}
	// Scripted chase camera for Minecraft-driven flight (elytra).
	inline Cam CreateCam(const char *name) { return invoke<Cam>(0xC3981DCE61D9E13F, name, TRUE); }
	inline void DestroyCam(Cam c) { invoke<Void>(0x865908C81A2C22E9, c, FALSE); }
	inline void SetCamCoord(Cam c, float x, float y, float z) { invoke<Void>(0x4D41783FB745E42E, c, x, y, z); }
	inline void SetCamRot(Cam c, float x, float y, float z) { invoke<Void>(0x85973643155D0B07, c, x, y, z, 2); }
	inline void SetCamFov(Cam c, float fov) { invoke<Void>(0xB13C14F66A00D047, c, fov); }
	inline void SetCamActive(Cam c, BOOL a) { invoke<Void>(0x026FB97D0A425F84, c, a); }
	inline void RenderScriptCams(BOOL render, BOOL ease = FALSE, int easeMs = 0) { invoke<Void>(0x07E5B515DB0636FC, render, ease, easeMs, TRUE, FALSE, 0); }
	inline float GetDisabledControlNormal(int group, int control) { return invoke<float>(0x11E65974A982637C, group, control); }
	inline BOOL IsPedFalling(Ped p) { return invoke<BOOL>(0xFB92A102F1C4DFA3, p); }
	inline BOOL IsPedInParachuteFreeFall(Ped p) { return invoke<BOOL>(0x7DCE8BDA0F1C1200, p); }
	inline Vector3 GetEntityVelocity(Entity e) { return invoke<Vector3>(0x4805D2B1D8CF94A9, e); }
	inline Vector3 GetGameplayCamRot(int order) { return invoke<Vector3>(0x837765A25378F0BB, order); }
	inline void SetEntityAlpha(Entity e, int alpha) { invoke<Void>(0x44A0870B7E92D7C0, e, alpha, FALSE); }
	inline int GetClockHours() { return invoke<int>(0x25223CA6B4D20B7F); }
	inline int GetClockMinutes() { return invoke<int>(0x13D2B8ADD79640F2); }

	inline void Notify(const char *text)
	{
		invoke<Void>(0x202709F4C58A0424, "STRING");
		invoke<Void>(0x6C188BE134E074AA, text);
		invoke<int>(0x2ED7843F8F801023, FALSE, FALSE);
	}
}

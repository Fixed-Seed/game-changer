using System;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.Audio;
using Terraria.GameContent;
using Terraria.GameContent.ItemDropRules;
using Terraria.ID;
using Terraria.ModLoader;

namespace SeedArsenal
{
	/// <summary>
	/// A boss that isn't in Terraria. Phase 1: circles high above the player, launches Scrap Drones
	/// and fires laser fans. Below half health it turns red: faster, dashes, and fires homing rockets.
	/// Vanilla boss plumbing: health bar, boss music, "has awoken!/has been defeated!" messages, loot.
	/// Summoned with /mothership.
	/// </summary>
	public class DroneMothership : ModNPC
	{
		public override string Texture => "SeedArsenal/Assets/DroneMothership";
		bool Phase2 => NPC.life < NPC.lifeMax / 2;

		public override void SetStaticDefaults()
		{
			Main.npcFrameCount[Type] = 2;
			NPCID.Sets.MPAllowedEnemies[Type] = true; // lets a multiplayer client ask the server to summon it
		}

		public override void SetDefaults()
		{
			NPC.width = 200; NPC.height = 90;
			NPC.lifeMax = 5200; NPC.damage = 28; NPC.defense = 8;
			NPC.boss = true; NPC.noGravity = true; NPC.noTileCollide = true; NPC.lavaImmune = true;
			NPC.knockBackResist = 0f; NPC.npcSlots = 10f;
			NPC.HitSound = SoundID.NPCHit4; NPC.DeathSound = SoundID.NPCDeath14;
			NPC.aiStyle = -1; NPC.value = Item.buyPrice(gold: 8);
			Music = MusicID.Boss2;
		}

		public override void AI()
		{
			NPC.TargetClosest();
			var p = Main.player[NPC.target];
			if (p.dead || !p.active) // nobody left to chase: fly off and despawn, like vanilla bosses
			{
				NPC.velocity.Y -= 0.1f;
				NPC.EncourageDespawn(10);
				return;
			}
			ref float t = ref NPC.ai[0];
			ref float dash = ref NPC.ai[1];
			t++;
			bool p2 = Phase2;
			if (dash > 0)
			{
				dash--;
				NPC.velocity *= 0.985f;
			}
			else
			{
				var hover = p.Center + new Vector2(MathF.Sin(t * 0.012f) * 250, -225 + MathF.Sin(t * 0.031f) * 30); // stays on screen
				NPC.velocity += (hover - NPC.Center).SafeNormalize(Vector2.Zero) * (p2 ? 0.3f : 0.18f);
				float max = p2 ? 9f : 6f;
				if (NPC.velocity.Length() > max) NPC.velocity = Vector2.Normalize(NPC.velocity) * max;
				NPC.velocity *= 0.985f;
				if (p2 && t % 260 == 0)
				{
					NPC.velocity = (p.Center - NPC.Center).SafeNormalize(Vector2.UnitY) * 15f;
					dash = 45;
					SoundEngine.PlaySound(SoundID.Roar with { Pitch = 0.4f }, NPC.Center);
				}
			}
			// caught in an orbital beam: held in place (and it can't dash out)
			foreach (var pr in Main.ActiveProjectiles)
				if (pr.ModProjectile is OrbitalBeam beam && beam.Firing && Math.Abs(pr.Center.X - NPC.Center.X) < 120)
				{
					NPC.velocity *= 0.8f;
					dash = 0;
				}
			// never sink into the ground (it ignores tiles)
			float ground = Fx.SurfaceTile((int)(NPC.Center.X / 16)) * 16f;
			if (NPC.Bottom.Y > ground - 80) NPC.velocity.Y = Math.Min(NPC.velocity.Y, -3f);
			NPC.rotation = NPC.velocity.X * 0.015f;
			var core = NPC.Center + new Vector2(0, 26);
			if (Main.netMode != NetmodeID.MultiplayerClient)
			{
				if (t % (p2 ? 55 : 85) == 30) // laser fan from the core
				{
					var baseDir = (p.Center - core).SafeNormalize(Vector2.UnitY);
					for (int k = -2; k <= 2; k++)
						Projectile.NewProjectile(NPC.GetSource_FromAI(), core, baseDir.RotatedBy(k * 0.22f) * 7.5f, ProjectileID.PinkLaser, 10, 0f);
					SoundEngine.PlaySound(SoundID.Item33, core);
				}
				if (!p2 && t % 150 == 75 && NPC.CountNPCS(ModContent.NPCType<ScrapDrone>()) < 5) // launch drones
					for (int s = -1; s <= 1; s += 2)
					{
						NPC.NewNPC(NPC.GetSource_FromAI(), (int)(NPC.Center.X + s * 80), (int)NPC.Bottom.Y, ModContent.NPCType<ScrapDrone>());
						SoundEngine.PlaySound(SoundID.Item149, NPC.Center);
					}
				if (p2 && t % 70 == 20) // homing rockets out of both wings
					for (int s = -1; s <= 1; s += 2)
						Projectile.NewProjectile(NPC.GetSource_FromAI(), NPC.Center + new Vector2(s * 90, 0), new Vector2(s * 5, -3), ModContent.ProjectileType<HostileRocket>(), 12, 0f);
			}
			Lighting.AddLight(core, p2 ? 1.2f : 0.9f, 0.15f, 0.1f);
			if (p2 && Main.rand.NextBool(3))
				Dust.NewDustPerfect(NPC.Center + Main.rand.NextVector2Circular(90, 30), DustID.Smoke, new Vector2(0, -1), 120, default, 1.6f).noGravity = true;
		}

		// frame 2 is the same hull with the red core flared: blinks faster in phase 2
		public override void FindFrame(int frameHeight) => NPC.frame.Y = (int)(NPC.ai[0] / (Phase2 ? 5 : 10) % 2) * frameHeight;

		public override Color? GetAlpha(Color drawColor) => Phase2 ? Color.Lerp(drawColor, new Color(255, 90, 80), 0.35f) : null;

		public override void HitEffect(NPC.HitInfo hit)
		{
			for (int i = 0; i < 4; i++)
				Dust.NewDustPerfect(NPC.Center + Main.rand.NextVector2Circular(90, 35), DustID.Electric, Main.rand.NextVector2Circular(4, 4), 0, default, 1f).noGravity = true;
			if (NPC.life <= 0)
				Fx.BigBoom(NPC.Center);
		}

		public override void BossLoot(ref int potionType) => potionType = ItemID.HealingPotion;

		public override void ModifyNPCLoot(NPCLoot loot)
		{
			loot.Add(ItemDropRule.Common(ItemID.GoldCoin, 1, 6, 9));
			loot.Add(ItemDropRule.Common(ItemID.SoulofFlight, 1, 8, 14));
			loot.Add(ItemDropRule.Common(ItemID.HallowedBar, 1, 10, 18));
		}
	}

	/// <summary>The Mothership's phase-2 rocket: steers toward the nearest player.</summary>
	public class HostileRocket : ModProjectile
	{
		public override string Texture => "SeedArsenal/Assets/HomingMissile";

		public override void SetDefaults()
		{
			Projectile.width = Projectile.height = 14;
			Projectile.hostile = true; Projectile.friendly = false;
			Projectile.tileCollide = false; Projectile.timeLeft = 240;
		}

		public override void AI()
		{
			var p = Main.player[Player.FindClosest(Projectile.position, Projectile.width, Projectile.height)];
			var dir = Projectile.velocity.SafeNormalize(Vector2.UnitX);
			if (Projectile.ai[0]++ > 15)
				dir = Vector2.Normalize(dir * 20f + (p.Center - Projectile.Center).SafeNormalize(dir));
			Projectile.velocity = dir * Math.Min(Projectile.velocity.Length() + 0.15f, 8.5f);
			Projectile.rotation = Projectile.velocity.ToRotation();
			Dust.NewDustPerfect(Projectile.Center - dir * 14, DustID.Torch, -dir * 2, 0, default, 1.5f).noGravity = true;
			Dust.NewDustPerfect(Projectile.Center - dir * 14, DustID.Smoke, Vector2.Zero, 120, default, 1.2f).noGravity = true;
		}

		public override bool PreDraw(ref Color lightColor)
		{
			var tex = TextureAssets.Projectile[Type].Value;
			Main.EntitySpriteDraw(tex, Projectile.Center - Main.screenPosition, null, new Color(255, 120, 110), Projectile.rotation, tex.Size() / 2, 1.1f, SpriteEffects.None);
			return false;
		}

		public override void OnKill(int timeLeft)
		{
			SoundEngine.PlaySound(SoundID.Item14 with { Volume = 0.6f }, Projectile.Center);
			Fx.SmallBoom(Projectile.Center, 1.1f);
		}
	}
}

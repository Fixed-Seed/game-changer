using System;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.Audio;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.Utilities;

namespace SeedArsenal
{
	// Enemies that aren't in Terraria. Sprites face left, like vanilla NPC sheets: spriteDirection 1
	// flips them to face right. Frames are stacked vertically; the game derives the frame height from
	// texture height / Main.npcFrameCount. They spawn on the surface now and then.

	/// <summary>Circles above the player, strafing, and fires lasers.</summary>
	public class ScrapDrone : ModNPC
	{
		public override string Texture => "SeedArsenal/Assets/ScrapDrone";
		public override void SetStaticDefaults() => Main.npcFrameCount[Type] = 2;

		public override void SetDefaults()
		{
			NPC.width = 40; NPC.height = 26;
			NPC.lifeMax = 70; NPC.damage = 12; NPC.defense = 4;
			NPC.noGravity = true; NPC.noTileCollide = true;
			NPC.knockBackResist = 0.6f;
			NPC.HitSound = SoundID.NPCHit4; NPC.DeathSound = SoundID.NPCDeath14;
			NPC.aiStyle = -1; NPC.value = 0;
		}

		public override float SpawnChance(NPCSpawnInfo spawnInfo) => SpawnCondition.Overworld.Chance * 0.04f;

		public override void AI()
		{
			NPC.TargetClosest();
			var p = Main.player[NPC.target];
			ref float timer = ref NPC.ai[0];
			ref float side = ref NPC.ai[1];
			timer++;
			if (side == 0 || timer % 200 == 0) side = Main.rand.NextBool() ? 1 : -1;
			var hover = p.Center + new Vector2(side * 230 + MathF.Sin(timer * 0.03f + NPC.whoAmI) * 90, -170 + MathF.Sin(timer * 0.05f) * 45);
			NPC.velocity += (hover - NPC.Center).SafeNormalize(Vector2.Zero) * 0.35f;
			if (NPC.velocity.Length() > 7) NPC.velocity = Vector2.Normalize(NPC.velocity) * 7;
			NPC.velocity *= 0.97f;
			NPC.rotation = NPC.velocity.X * 0.05f;
			NPC.spriteDirection = NPC.direction = p.Center.X > NPC.Center.X ? 1 : -1;
			if (timer % 95 == 60 && Main.netMode != NetmodeID.MultiplayerClient)
			{
				var v = (p.Center - NPC.Center).SafeNormalize(Vector2.UnitY) * 7f;
				Projectile.NewProjectile(NPC.GetSource_FromAI(), NPC.Center, v, ProjectileID.PinkLaser, 8, 0f);
				SoundEngine.PlaySound(SoundID.Item12, NPC.Center);
			}
			Lighting.AddLight(NPC.Center, 0.6f, 0.1f, 0.1f);
		}

		public override void FindFrame(int frameHeight) => NPC.frame.Y = (int)(NPC.ai[0] / 4 % 2) * frameHeight;

		public override void HitEffect(NPC.HitInfo hit)
		{
			for (int i = 0; i < (NPC.life <= 0 ? 30 : 6); i++)
				Dust.NewDustPerfect(NPC.Center, DustID.Electric, Main.rand.NextVector2Circular(5, 5), 0, default, 1.2f).noGravity = true;
			if (NPC.life <= 0) Fx.SmallBoom(NPC.Center);
		}
	}

	/// <summary>A glowing slime (vanilla slime AI).</summary>
	public class NeonSlime : ModNPC
	{
		public override string Texture => "SeedArsenal/Assets/NeonSlime";
		public override void SetStaticDefaults() => Main.npcFrameCount[Type] = 2;

		public override void SetDefaults()
		{
			NPC.width = 34; NPC.height = 28;
			NPC.lifeMax = 60; NPC.damage = 12; NPC.defense = 2;
			NPC.knockBackResist = 0.8f;
			NPC.HitSound = SoundID.NPCHit1; NPC.DeathSound = SoundID.NPCDeath1;
			NPC.aiStyle = NPCAIStyleID.Slime; AIType = NPCID.BlueSlime; AnimationType = NPCID.BlueSlime;
			NPC.value = 0;
		}

		public override float SpawnChance(NPCSpawnInfo spawnInfo) => SpawnCondition.OverworldDaySlime.Chance * 0.1f;

		public override void PostAI() => Lighting.AddLight(NPC.Center, 0.1f, 0.6f, 0.7f);

		public override void HitEffect(NPC.HitInfo hit)
		{
			for (int i = 0; i < (NPC.life <= 0 ? 35 : 8); i++)
				Dust.NewDustPerfect(NPC.Center, DustID.BlueTorch, Main.rand.NextVector2Circular(4, 4), 0, default, 1.6f).noGravity = true;
		}
	}

	/// <summary>Walks at the player and hops over steps and gaps. Custom AI because vanilla fighter
	/// AI (aiStyle 3) stops chasing on the surface in daytime: it wanders off and despawns.</summary>
	public class MechWalker : ModNPC
	{
		public override string Texture => "SeedArsenal/Assets/MechWalker";
		public override void SetStaticDefaults() => Main.npcFrameCount[Type] = 3;

		public override void SetDefaults()
		{
			NPC.width = 26; NPC.height = 44;
			NPC.lifeMax = 90; NPC.damage = 15; NPC.defense = 6;
			NPC.knockBackResist = 0.5f;
			NPC.HitSound = SoundID.NPCHit4; NPC.DeathSound = SoundID.NPCDeath14;
			NPC.aiStyle = -1; NPC.value = 0;
		}

		public override float SpawnChance(NPCSpawnInfo spawnInfo) => SpawnCondition.Overworld.Chance * 0.04f;

		public override void AI()
		{
			NPC.TargetClosest();
			var p = Main.player[NPC.target];
			int dir = p.Center.X > NPC.Center.X ? 1 : -1;
			NPC.direction = NPC.spriteDirection = dir;
			float speed = 2.4f;
			if (NPC.velocity.X * dir < speed) NPC.velocity.X += dir * 0.12f;
			if (Math.Abs(NPC.velocity.X) > speed + 1) NPC.velocity.X *= 0.9f;
			Collision.StepUp(ref NPC.position, ref NPC.velocity, NPC.width, NPC.height, ref NPC.stepSpeed, ref NPC.gfxOffY);
			bool grounded = NPC.velocity.Y == 0;
			if (grounded && (NPC.collideX || (p.Bottom.Y < NPC.Top.Y - 16 && Math.Abs(p.Center.X - NPC.Center.X) < 160) || Main.rand.NextBool(240)))
				NPC.velocity.Y = -7.5f;
			NPC.ai[0] += Math.Abs(NPC.velocity.X);
			Lighting.AddLight(NPC.Center, 0.2f, 0.6f, 0.2f);
		}

		// frame 1 (upright) while airborne, else a 3-frame rocking walk driven by distance covered
		public override void FindFrame(int frameHeight) => NPC.frame.Y = NPC.velocity.Y != 0 ? frameHeight : (int)(NPC.ai[0] / 14 % 3) * frameHeight;

		public override void HitEffect(NPC.HitInfo hit)
		{
			for (int i = 0; i < (NPC.life <= 0 ? 25 : 6); i++)
				Dust.NewDustPerfect(NPC.Center, i % 2 == 0 ? DustID.Electric : DustID.Smoke, Main.rand.NextVector2Circular(4, 4), 0, default, 1.3f).noGravity = true;
			if (NPC.life <= 0) Fx.SmallBoom(NPC.Center);
		}
	}
}

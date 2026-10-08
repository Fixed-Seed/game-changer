using System;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.Audio;
using Terraria.DataStructures;
using Terraria.GameContent;
using Terraria.Graphics.CameraModifiers;
using Terraria.ID;
using Terraria.ModLoader;

namespace SeedArsenal
{
	// Explosives. Item sprites point right (vanilla convention); the recipes are cheap on purpose so
	// the mod can be tried without the /arsenal command.

	public class HomingMissileLauncher : ModItem
	{
		public override string Texture => "SeedArsenal/Assets/HomingMissileLauncher";

		public override void SetDefaults()
		{
			Item.width = 64; Item.height = 26;
			Item.useStyle = ItemUseStyleID.Shoot;
			Item.useTime = Item.useAnimation = 20;
			Item.autoReuse = true;
			Item.damage = 60;
			Item.DamageType = DamageClass.Ranged;
			Item.knockBack = 4f;
			Item.noMelee = true;
			Item.shoot = ModContent.ProjectileType<HomingMissile>();
			Item.shootSpeed = 7f;
			Item.UseSound = SoundID.Item61;
			Item.rare = ItemRarityID.Yellow;
		}

		public override Vector2? HoldoutOffset() => new Vector2(-14, 2);

		public override void AddRecipes() => CreateRecipe()
			.AddRecipeGroup(RecipeGroupID.IronBar, 8)
			.AddIngredient(ItemID.Gel, 10)
			.AddTile(TileID.Anvils)
			.Register();
	}

	public class HomingMissile : ModProjectile
	{
		public override string Texture => "SeedArsenal/Assets/HomingMissile";

		public override void SetDefaults()
		{
			Projectile.width = Projectile.height = 14;
			Projectile.friendly = true;
			Projectile.DamageType = DamageClass.Ranged;
			Projectile.penetrate = 1;
			Projectile.timeLeft = 300;
			Projectile.tileCollide = true;
		}

		public override void AI()
		{
			NPC target = null;
			float best = 1400f;
			foreach (var n in Main.ActiveNPCs)
			{
				float d = Vector2.Distance(n.Center, Projectile.Center);
				if (d < best && n.CanBeChasedBy(Projectile)) { best = d; target = n; }
			}
			float speed = Math.Min(Projectile.velocity.Length() + 0.3f, 15f);
			var dir = Projectile.velocity.SafeNormalize(Vector2.UnitX);
			if (target != null && Projectile.ai[0]++ > 6)
				dir = Vector2.Normalize(dir * 9f + (target.Center - Projectile.Center).SafeNormalize(dir));
			Projectile.velocity = dir * speed;
			Projectile.rotation = Projectile.velocity.ToRotation();
			var tail = Projectile.Center - dir * 16f;
			Dust.NewDustPerfect(tail, DustID.Torch, -dir * 2f + Main.rand.NextVector2Circular(1, 1), 0, default, 1.8f).noGravity = true;
			var smoke = Dust.NewDustPerfect(tail, DustID.Smoke, Main.rand.NextVector2Circular(0.6f, 0.6f), 120, default, 1.6f);
			smoke.noGravity = true;
			Lighting.AddLight(tail, 1f, 0.6f, 0.2f);
		}

		public override bool PreDraw(ref Color lightColor)
		{
			var tex = TextureAssets.Projectile[Type].Value;
			Main.EntitySpriteDraw(tex, Projectile.Center - Main.screenPosition, null, Color.White, Projectile.rotation, tex.Size() / 2, 1.2f, SpriteEffects.None);
			return false;
		}

		public override void OnKill(int timeLeft)
		{
			var c = Projectile.Center;
			SoundEngine.PlaySound(SoundID.Item14, c);
			for (int i = 0; i < 28; i++)
				Dust.NewDustPerfect(c, DustID.Smoke, Main.rand.NextVector2Circular(5, 5), 100, default, 2.2f).noGravity = true;
			for (int i = 0; i < 22; i++)
				Dust.NewDustPerfect(c, DustID.Torch, Main.rand.NextVector2Circular(7, 7), 0, default, 2.6f).noGravity = true;
			for (int i = 0; i < 3; i++)
				Gore.NewGoreDirect(Projectile.GetSource_Death(), c - new Vector2(24), Main.rand.NextVector2Circular(1.5f, 1.5f), GoreID.Smoke1 + Main.rand.Next(3), 1.2f);
			Main.instance.CameraModifiers.Add(new PunchCameraModifier(c, Main.rand.NextVector2Unit(), 3f, 8f, 12, 1200f));
			Fx.SmallBoom(c, 1.4f);
			if (Projectile.owner != Main.myPlayer) return;
			// splash damage + a small crater (like Rocket II)
			foreach (var n in Main.ActiveNPCs)
				if (!n.friendly && n.life > 0 && Vector2.Distance(n.Center, c) < 80f && n.whoAmI != (int)Projectile.localAI[0] - 1)
					n.SimpleStrikeNPC(Projectile.damage / 2, Math.Sign(n.Center.X - c.X));
			Fx.Blast(c, 3);
		}

		public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone) => Projectile.localAI[0] = target.whoAmI + 1;
	}

	/// <summary>Calls a warhead down 60 tiles in front of you. Not consumed.</summary>
	public class TacticalNuke : ModItem
	{
		public override string Texture => "SeedArsenal/Assets/TacticalNuke";

		public override void SetDefaults()
		{
			Item.width = 40; Item.height = 84;
			Item.useStyle = ItemUseStyleID.HoldUp;
			Item.useTime = Item.useAnimation = 45;
			Item.UseSound = SoundID.Item113;
			Item.rare = ItemRarityID.Red;
		}

		public override bool? UseItem(Player player)
		{
			if (player.whoAmI != Main.myPlayer || player.ownedProjectileCounts[ModContent.ProjectileType<NukeWarhead>()] > 0) return true;
			var target = player.Center + new Vector2(player.direction * 60 * 16, 0);
			float groundY = Fx.SurfaceTile((int)(target.X / 16)) * 16f;
			Projectile.NewProjectile(player.GetSource_ItemUse(Item), new Vector2(target.X, groundY - 60 * 16), new Vector2(0, 12f),
				ModContent.ProjectileType<NukeWarhead>(), 0, 0, player.whoAmI, groundY);
			Main.NewText("WARNING: tactical nuke inbound!", new Color(255, 80, 40));
			return true;
		}

		public override void AddRecipes() => CreateRecipe()
			.AddRecipeGroup(RecipeGroupID.IronBar, 12)
			.AddIngredient(ItemID.FallenStar, 5)
			.AddTile(TileID.Anvils)
			.Register();
	}

	/// <summary>Falls onto ground level (ai[0], set at launch) and detonates there.</summary>
	public class NukeWarhead : ModProjectile
	{
		public override string Texture => "SeedArsenal/Assets/TacticalNuke";

		public override void SetDefaults()
		{
			Projectile.width = 40; Projectile.height = 84;
			Projectile.tileCollide = false;
			Projectile.timeLeft = 900;
			Projectile.friendly = Projectile.hostile = false;
		}

		Vector2 GroundZero => new(Projectile.Center.X, Projectile.ai[0]);

		// the owner's camera goes over to ground zero while it falls (spawning only runs on the owner)
		public override void OnSpawn(IEntitySource source) => Fx.Focus(GroundZero - new Vector2(0, 12 * 16), 60);

		public override void AI()
		{
			Projectile.velocity.Y = Math.Min(Projectile.velocity.Y + 0.6f, 30f);
			var top = Projectile.Top + new Vector2(0, 8);
			for (int i = 0; i < 3; i++)
				Dust.NewDustPerfect(top + Main.rand.NextVector2Circular(8, 4), DustID.Torch, new Vector2(0, -3) + Main.rand.NextVector2Circular(1.5f, 1.5f), 0, default, 2.4f).noGravity = true;
			Dust.NewDustPerfect(top, DustID.Smoke, new Vector2(0, -1) + Main.rand.NextVector2Circular(1, 1), 100, default, 2.4f).noGravity = true;
			Lighting.AddLight(Projectile.Center, 1.2f, 0.7f, 0.3f);
			if (Projectile.Bottom.Y >= Projectile.ai[0])
			{
				Fx.Detonate(GroundZero);
				if (Projectile.owner == Main.myPlayer) Fx.Focus(GroundZero - new Vector2(0, 12 * 16), 150); // stay for the cloud
				Projectile.Kill();
			}
		}

		public override bool PreDraw(ref Color lightColor)
		{
			var tex = TextureAssets.Projectile[Type].Value;
			Main.EntitySpriteDraw(tex, Projectile.Center - Main.screenPosition, null, Color.White, 0f, tex.Size() / 2, 1.4f, SpriteEffects.None);
			return false;
		}
	}
}

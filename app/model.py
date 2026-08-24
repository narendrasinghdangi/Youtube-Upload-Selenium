"""
model.py

Shared Video data model.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Video:
    video_title: str
    video_description: str
    thumbnail_file_path: str
    video_file_path: str
    tags: list[str] = field(default_factory=list)
    language: str = "en"
    ai_generated: bool = True  # flag as AI-generated on both YouTube and Instagram
    category: str = "Comedy"  # YouTube video category (e.g. "Comedy", "Education", "Gaming")

    def build_caption(self) -> str:
        """Instagram reels/posts don't have a separate 'title' field like
        YouTube — everything goes in one caption. This folds title +
        description + hashtags into a single caption string."""
        parts = []
        if self.video_title:
            parts.append(self.video_title)
        if self.video_description:
            parts.append(self.video_description)
        caption = "\n\n".join(parts)

        if self.tags:
            hashtags = " ".join(
                t if t.startswith("#") else f"#{t}" for t in self.tags
            )
            caption = f"{caption}\n\n{hashtags}" if caption else hashtags

        return caption


image_system_prompt: str = """# Video Thumbnail Generator Prompt

You are an AI image generator creating viral, professional video thumbnails.
Use realistic, cinematic visuals with relevant people, objects, and backgrounds.
Make the main subject prominent with dramatic, bright, and clean lighting.
Add a bold, short, highly readable headline based on the title.
Highlight important keywords, names, numbers, or facts with contrasting colors.
Place text naturally without covering the main subject.
Use strong contrast, depth, and visual hierarchy to attract attention.
Maintain a clean **16:9 landscape composition** optimized for video thumbnails.
Avoid clutter, excessive text, blurry visuals, distorted faces, and poor typography.
Create the thumbnail using **Title: {video_title}** and **Description: {video_description}**.
"""


video_system_prompt: str = """# Video Generator Prompt

You are an AI video generator creating realistic, informative, social-media-style news videos.
Create a visually engaging video based on the provided title and description.
Use realistic people, objects, locations, and environments relevant to the story.
Generate cinematic, high-quality visuals with professional lighting.
Keep the visual style realistic, modern, clean, and news-like.
Create multiple scenes that naturally explain the story from beginning to end.
Ensure smooth transitions between scenes.
Use natural camera movements such as zooms, pans, tracking, and close-ups.
Maintain consistent characters, clothing, locations, and visual appearance.
Use realistic facial expressions, body movements, and interactions.
Match the visuals closely with the information provided in the description.
Keep the pacing dynamic and engaging for social media audiences.
Emphasize important events, facts, numbers, and key moments visually.
Use appropriate background environments and contextual elements.
Maintain clear visual storytelling without unnecessary or unrelated scenes.
Avoid distorted faces, unrealistic movements, flickering, glitches, and artifacts.
Avoid excessive visual effects that reduce realism or clarity.
Keep the overall tone informative, attention-grabbing, and professional.
Generate the video in a vertical **9:16 format** optimized for social media.
Create the video using **Title: {video_title}** and **Description: {video_description}**.

"""

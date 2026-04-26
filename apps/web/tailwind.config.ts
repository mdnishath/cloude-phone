import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0a",
        card: "#171717",
        border: "#262626",
      },
    },
  },
  plugins: [],
};

export default config;

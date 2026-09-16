import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#12213a",
        navy: "#123660",
        line: "#d9e5f2",
      },
      boxShadow: {
        shell: "0 18px 55px rgba(20, 51, 88, 0.22)",
      },
    },
  },
  plugins: [],
};

export default config;

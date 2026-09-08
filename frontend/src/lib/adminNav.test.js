import { navigationGroups } from "./adminNav";

function allItems() {
  return navigationGroups.flatMap((group) => group.children || []);
}

test("shows only the advanced email marketing entry under Marketing", () => {
  const entries = allItems().filter((item) =>
    /e-?posta|toplu mail/i.test(String(item.label || ""))
  );

  expect(entries).toHaveLength(1);
  expect(entries[0]).toMatchObject({
    label: "E-posta Pazarlama",
    path: "/admin/eposta-pazarlama",
  });

  const marketing = navigationGroups.find((group) => group.label === "Pazarlama");
  expect(marketing?.children).toContain(entries[0]);
});

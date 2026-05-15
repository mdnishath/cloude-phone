import { Button } from '@/components/ui/button';

export const App = (): JSX.Element => (
  <div className="p-6 space-y-4">
    <h1 className="text-2xl font-semibold">Cloude Phone</h1>
    <p className="text-muted-foreground">Tailwind + shadcn smoke. Replace with router in Task 9.</p>
    <Button>Primary</Button>
    <Button variant="outline">Outline</Button>
    <Button variant="destructive">Destructive</Button>
  </div>
);

import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'screens/dashboard_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  await Supabase.initialize(
    url: 'https://gqlrhlxtzbtwthdlmiup.supabase.co',
    anonKey: 'sb_publishable_Xv1lemXh8As0I8ssTSyA6Q_XUMN_1vf',
  );
  
  runApp(const SarkariJobsApp());
}

class SarkariJobsApp extends StatelessWidget {
  const SarkariJobsApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Sarkari Jobs',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        visualDensity: VisualDensity.adaptivePlatformDensity,
      ),
      home: const DashboardScreen(),
    );
  }
}